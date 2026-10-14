"""Offline regression checks for notebook forecasting boundaries."""
import ast
import json
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fastf1
import numpy as np
import pandas as pd
import trueskill
from catboost import CatBoostClassifier, CatBoostRanker, CatBoostRegressor, Pool
from scipy.optimize import minimize
from scipy.stats import norm
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import (HistGradientBoostingClassifier, HistGradientBoostingRegressor,
                              RandomForestClassifier, RandomForestRegressor)
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_selection import VarianceThreshold
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import (BayesianRidge, ElasticNetCV, LassoCV, LinearRegression,
                                  LogisticRegression, QuantileRegressor, Ridge)
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from statsmodels.miscmodels.ordinal_model import OrderedModel
from statsmodels.regression.mixed_linear_model import MixedLM
from statsmodels.tools.sm_exceptions import ConvergenceWarning as SMConvergenceWarning, HessianInversionWarning

NB = json.loads((Path(__file__).resolve().parents[1] / 'f1_race_prediction.ipynb').read_text())
NS = dict(fastf1=fastf1, np=np, pd=pd, warnings=warnings, trueskill=trueskill, SimpleImputer=SimpleImputer,
          Ridge=Ridge, make_pipeline=make_pipeline, StandardScaler=StandardScaler, CatBoostRanker=CatBoostRanker,
          Pool=Pool, mean_absolute_error=mean_absolute_error, LogisticRegression=LogisticRegression,
          HistGradientBoostingClassifier=HistGradientBoostingClassifier, CatBoostClassifier=CatBoostClassifier,
          CatBoostRegressor=CatBoostRegressor, minimize=minimize, norm=norm,
          TransformedTargetRegressor=TransformedTargetRegressor,
          HistGradientBoostingRegressor=HistGradientBoostingRegressor, RandomForestClassifier=RandomForestClassifier,
          RandomForestRegressor=RandomForestRegressor, ConvergenceWarning=ConvergenceWarning,
          VarianceThreshold=VarianceThreshold, GaussianProcessRegressor=GaussianProcessRegressor, RBF=RBF,
          ConstantKernel=ConstantKernel, WhiteKernel=WhiteKernel, IsotonicRegression=IsotonicRegression,
          BayesianRidge=BayesianRidge, ElasticNetCV=ElasticNetCV, LassoCV=LassoCV, LinearRegression=LinearRegression,
          QuantileRegressor=QuantileRegressor, GroupKFold=GroupKFold, MLPClassifier=MLPClassifier,
          MLPRegressor=MLPRegressor, OrderedModel=OrderedModel, MixedLM=MixedLM,
          SMConvergenceWarning=SMConvergenceWarning, HessianInversionWarning=HessianInversionWarning)
# Every literal setting in the notebook's configuration cell is read from it, so the tests
# exercise the configured values rather than a copy. Settings that are not literals, and
# smaller models and simulations for speed, are set below.
CONFIG = next(c for c in NB['cells'] if c['cell_type'] == 'code' and 'SESSION_CODES' in ''.join(c['source']))
for statement in ast.parse(''.join(CONFIG['source'])).body:
    if isinstance(statement, ast.Assign) and isinstance(statement.targets[0], ast.Name):
        try:
            NS[statement.targets[0].id] = ast.literal_eval(statement.value)
        except ValueError:
            pass
PODIUM_METHODS = ['Grid order', 'Qualifying order', 'Prior finish', 'Ridge pace', 'CatBoost',
                  'Logistic', 'Shallow tree', 'Simulation', 'Grid-slot rate',
                  'PairLogit', 'Plackett-Luce', 'Bradley-Terry', 'Elo', 'Glicko-2', 'TrueSkill',
                  'Ordinal logit', 'Random forest', 'CatBoost classifier', 'MLP',
                  'Logistic + isotonic', 'Shallow tree + isotonic', 'Lap simulation',
                  'Rank average', 'Probability average']
PROB_METHODS = ['Logistic', 'Shallow tree', 'Simulation', 'Grid-slot rate', 'Plackett-Luce', 'Ordinal logit',
                'Random forest', 'CatBoost classifier', 'MLP', 'Logistic + isotonic', 'Shallow tree + isotonic',
                'Lap simulation', 'Probability average']
NS.update(FEATURES=['QualiRatio', 'QualifyingPosition', 'PriorPace'],
          EWM_FEATURES=['QualiRatio', 'QualifyingPosition', 'EwmPace'],
          KALMAN_FEATURES=['QualiRatio', 'QualifyingPosition', 'KalmanPace'],
          FINISH_FEATURES=['QualiRatio', 'GridPosition', 'PriorFinish'],
          CATBOOST_PARAMS=dict(loss_function='YetiRank', depth=2, iterations=20, random_seed=0, verbose=False),
          TREE_PARAMS=dict(max_depth=2, max_iter=10, min_samples_leaf=2, random_state=0),
          FOREST_PARAMS=dict(n_estimators=20, min_samples_leaf=2, random_state=0),
          GBM_PARAMS=dict(depth=2, iterations=20, random_seed=0, verbose=False, allow_writing_files=False),
          MLP_PARAMS=dict(hidden_layer_sizes=(4,), alpha=1.0, solver='lbfgs', max_iter=500, random_state=0),
          ELO_START=1500.0, ELO_K=32.0, GLICKO_START_RD=350.0, GLICKO_START_VOL=0.06, GLICKO_TAU=0.5,
          SPRINT_DISTANCE=1 / 3, N_SIMULATIONS=500, N_BOOTSTRAP=200, LAPSIM_SIMULATIONS=300,
          LAPSIM_DEFAULTS=dict(race=dict(RaceLaps=50, PitLossRatio=0.2, StopsPerDriver=1, DegPerLap=0.0005, SCPerLap=0.02),
                               sprint=dict(RaceLaps=17, PitLossRatio=0.2, StopsPerDriver=0, DegPerLap=0.0005, SCPerLap=0.02)))
for cell in NB['cells']:
    if cell['cell_type'] == 'code':
        tree = ast.parse(''.join(cell['source']))
        definitions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        exec(compile(ast.Module(body=definitions, type_ignores=[]), '<notebook>', 'exec'), NS)


def quali_results():
    return pd.DataFrame(dict(Abbreviation=['AAA', 'BBB'], DriverNumber=['1', '2'], FirstName=['A', 'B'],
        LastName=['One', 'Two'], TeamName=['X', 'Y'], Position=[1., 2.],
        Q1=pd.to_timedelta([90., 90.5], unit='s'), Q2=pd.to_timedelta([None, None]), Q3=pd.to_timedelta([None, None])))


class PredictionTests(unittest.TestCase):
    def test_form_uses_dates_not_names(self):
        frame = pd.DataFrame(dict(Driver=['A']*3, RaceId=['Alpha', 'Zulu', 'Bravo'],
                                  RaceStartUtc=pd.to_datetime(['2026-03-03', '2026-03-01', '2026-03-02'], utc=True),
                                  PaceRatio=[3., 1., 2.]))
        actual = NS['add_prior_form'](frame)
        self.assertEqual(actual.RaceId.tolist(), ['Zulu', 'Bravo', 'Alpha'])
        np.testing.assert_allclose(actual.PriorPace, [np.nan, 1., 1.5], equal_nan=True)

    def test_schedule_excludes_target_and_future_and_checks_venue(self):
        rows = []
        for i, (name, date, loc) in enumerate([('Earlier', '2026-09-26', 'Baku'),
                ('Bahrain Grand Prix', '2026-10-04', 'Kuala Lumpur'), ('Later', '2026-10-11', 'Singapore')]):
            row = dict(EventName=name, Location=loc, RoundNumber=i+1)
            for j in range(1, 6):
                row[f'Session{j}'] = 'Race' if j == 5 else 'Practice'
            row['Session5DateUtc'] = date
            rows.append(row)
        schedule = pd.DataFrame(rows)
        with patch.object(fastf1, 'get_event_schedule', return_value=schedule):
            _, earlier = NS['resolve_schedule'](2026, 'Bahrain Grand Prix')
            self.assertEqual(earlier.EventName.tolist(), ['Earlier'])
            schedule.loc[1, 'Location'] = 'Sakhir'
            with self.assertRaises(ValueError):
                NS['resolve_schedule'](2026, 'Bahrain Grand Prix')

    def test_sprint_schedule_rows_exclude_target_weekend_and_check_venue(self):
        def event(name, loc, rnd, sessions):
            row = dict(EventName=name, Location=loc, RoundNumber=rnd)
            names = ['Practice 1', 'Practice 2', 'Practice 3', 'Qualifying', 'Race']
            if 'Sprint' in sessions:
                names = ['Practice 1', 'Sprint Qualifying', 'Sprint', 'Qualifying', 'Race']
            for j, session in enumerate(names, 1):
                row[f'Session{j}'] = session
                row[f'Session{j}DateUtc'] = sessions.get(session)
            return row
        # Alphabetical order differs from date order, and Zandvoort's sprint precedes its race.
        schedule = pd.DataFrame([
            event('Zandvoort', 'Zandvoort', 1, {'Sprint': '2026-08-22 10:00', 'Race': '2026-08-23 13:00'}),
            event('Baku', 'Baku', 2, {'Race': '2026-09-26 11:00'}),
            event('Singapore Grand Prix', 'Marina Bay', 3, {'Sprint Qualifying': '2026-10-09 12:30',
                  'Sprint': '2026-10-10 09:00', 'Qualifying': '2026-10-10 13:00', 'Race': '2026-10-11 12:00'}),
            event('Austin', 'Austin', 4, {'Race': '2026-10-25 19:00'})])
        resolve = NS['resolve_schedule']
        with patch.object(fastf1, 'get_event_schedule', return_value=schedule):
            target, earlier = resolve(2026, 'Singapore Grand Prix', 'sprint')
            self.assertEqual((target.Kind, target.RaceStartUtc), ('sprint', pd.Timestamp('2026-10-10 09:00', tz='UTC')))
            self.assertEqual(list(zip(earlier.EventName, earlier.Kind)),
                             [('Zandvoort', 'sprint'), ('Zandvoort', 'race'), ('Baku', 'race')])
            self.assertTrue(earlier.RaceStartUtc.is_monotonic_increasing)
            self.assertTrue((earlier.RaceStartUtc < target.RaceStartUtc).all())
            # The weekend's own GP is a later session; as a race target it trains on the sprint.
            _, before_gp = resolve(2026, 'Singapore Grand Prix', 'race')
            self.assertEqual(before_gp.Kind.tolist()[-1], 'sprint')
            self.assertEqual(before_gp.EventName.tolist()[-1], 'Singapore Grand Prix')
            with self.assertRaises(ValueError):
                resolve(2026, 'Baku', 'sprint')  # no sprint at a conventional event
            schedule.loc[2, 'Session3DateUtc'] = '2026-10-03 09:00'
            with self.assertRaises(ValueError):
                resolve(2026, 'Singapore Grand Prix', 'sprint')  # wrong date
            schedule.loc[2, 'Session3DateUtc'] = '2026-10-10 09:00'
            schedule.loc[2, 'Location'] = 'Sakhir'
            with self.assertRaises(ValueError):
                resolve(2026, 'Singapore Grand Prix', 'sprint')  # wrong venue

    def test_sprint_target_loads_only_sprint_qualifying(self):
        session = SimpleNamespace(results=quali_results(), load=lambda **kwargs: None)
        with patch.object(fastf1, 'get_session', return_value=session) as load:
            frame = NS['build_race_frame'](2026, 17, False, kind='sprint')
        load.assert_called_once_with(2026, 17, 'SQ')
        self.assertEqual(frame.RaceId.unique().tolist(), ['2026 17 Sprint'])
        self.assertEqual(frame.Kind.unique().tolist(), ['sprint'])
        self.assertTrue(frame.PaceRatio.isna().all())

    def test_sprint_training_session_loads_sq_and_s(self):
        laps = pd.DataFrame(dict(Driver=['AAA'] * 3 + ['BBB'] * 3,
            LapTime=pd.to_timedelta([100., 100.5, 140., 101., 101.5, 102.], unit='s'),
            PitInTime=pd.NaT, PitOutTime=pd.NaT))
        results = pd.DataFrame(dict(Abbreviation=['AAA', 'BBB'], Position=[1., 2.], GridPosition=[1., 0.],
                                    ClassifiedPosition=['1', 'R']))
        sessions = {'SQ': SimpleNamespace(results=quali_results(), load=lambda **kwargs: None),
                    'S': SimpleNamespace(results=results, laps=laps, load=lambda **kwargs: None)}
        with patch.object(fastf1, 'get_session', side_effect=lambda y, e, code: sessions[code]) as load:
            frame = NS['build_race_frame'](2026, 4, True, kind='sprint')
        self.assertEqual([c.args for c in load.call_args_list], [(2026, 4, 'SQ'), (2026, 4, 'S')])
        self.assertEqual(frame.RaceId.unique().tolist(), ['2026 4 Sprint'])
        self.assertEqual(frame.GridPosition.tolist(), [1., 2.])  # pit-lane start goes to the back
        self.assertEqual(frame.NotClassified.tolist(), [False, True])
        self.assertLess(frame.PaceRatio.iloc[0], frame.PaceRatio.iloc[1])
        with patch.object(fastf1, 'get_session', side_effect=lambda y, e, code: sessions['SQ']) as load:
            NS['build_race_frame'](2026, 4, False)
        load.assert_called_once_with(2026, 4, 'Q')

    def test_weekend_sprint_feeds_gp_prior_pace_not_the_reverse(self):
        frame = pd.DataFrame(dict(Driver=['A'] * 3, RaceId=['2026 2', '2026 1', '2026 2 Sprint'],
            Kind=['race', 'race', 'sprint'], PaceRatio=[4., 1., 2.],
            RaceStartUtc=pd.to_datetime(['2026-03-08 13:00', '2026-03-01 13:00', '2026-03-07 10:00'], utc=True)))
        actual = NS['add_prior_form'](frame)
        self.assertEqual(actual.RaceId.tolist(), ['2026 1', '2026 2 Sprint', '2026 2'])
        self.assertEqual(actual.RaceIndex.tolist(), [0, 1, 2])
        np.testing.assert_allclose(actual.PriorPace, [np.nan, 1., 1.5], equal_nan=True)

    def test_sprint_only_filters_columns_and_index(self):
        frame = pd.DataFrame(dict(RaceId=['r1', 's2', 'r2'], Kind=['race', 'sprint', 'race']))
        walk = pd.DataFrame(dict(RaceId=['r1', 's2', 's2', 'r2'], Driver=list('ABAB')))
        self.assertEqual(NS['sprint_only'](walk, frame).Driver.tolist(), ['B', 'A'])
        per_race = walk.set_index(['RaceId', 'Driver'])
        self.assertEqual(NS['sprint_only'](per_race, frame).index.get_level_values('RaceId').unique().tolist(), ['s2'])
        self.assertTrue(NS['sprint_only'](pd.DataFrame(), frame).empty)

    def test_venue_keys_match_renamed_locations(self):
        self.assertEqual(NS['venue_key']('Miami Gardens'), NS['venue_key']('Miami'))
        self.assertEqual(NS['venue_key']('Monte Carlo'), NS['venue_key']('Monaco'))
        self.assertEqual(NS['venue_key'](' Marina Bay '), 'marina bay')
        self.assertNotEqual(NS['venue_key']('Kuala Lumpur'), NS['venue_key']('Sakhir'))

    def test_venue_history_loads_only_earlier_seasons_at_requested_venues(self):
        def schedule(season):
            rows = []
            for rnd, (loc, sprint) in enumerate([('Marina Bay', False), ('Miami', True), ('Monza', False)], 1):
                names = ['Practice 1', 'Sprint Qualifying' if sprint else 'Practice 2', 'Sprint' if sprint else 'Practice 3',
                         'Qualifying', 'Race']
                rows.append(dict(EventName=f'{loc} GP', Location=loc, RoundNumber=rnd,
                                 **{f'Session{i}': n for i, n in enumerate(names, 1)}))
            return pd.DataFrame(rows)
        calls = []
        def quali(year, rnd, code):
            calls.append((year, rnd, code))
            return pd.DataFrame(dict(Driver=['AAA'], QualiRatio=[1.01]))
        def outcome(year, rnd, code):
            calls.append((year, rnd, code))
            if (year, code) == (2024, 'R'):
                raise ValueError('No usable R laps')
            return pd.DataFrame(dict(Driver=['AAA'], PaceRatio=[0.99]))
        with patch.object(fastf1, 'get_event_schedule', side_effect=lambda season, **kw: schedule(season)) as sched, \
                patch.dict(NS, get_quali_frame=quali, get_race_outcome=outcome, VENUE_HISTORY_SEASONS=(2024, 2025)):
            history = NS['load_venue_history']({'marina bay', 'miami'}, 2026)
            self.assertEqual([c.args[0] for c in sched.call_args_list], [2024, 2025])
            with self.assertRaises(ValueError):
                with patch.dict(NS, VENUE_HISTORY_SEASONS=(2025, 2026)):
                    NS['load_venue_history']({'marina bay'}, 2026)
        self.assertEqual(calls, [(2024, 1, 'Q'), (2024, 1, 'R'), (2024, 2, 'Q'), (2024, 2, 'S'), (2024, 2, 'R'),
                                 (2025, 1, 'Q'), (2025, 1, 'R'), (2025, 2, 'Q'), (2025, 2, 'S'), (2025, 2, 'R')])
        self.assertTrue((history.Season < 2026).all())
        self.assertEqual(set(history.Venue), {'marina bay', 'miami'})
        self.assertEqual(len(history), 8)  # two failed 2024 race loads are skipped

    def test_venue_history_means_per_driver_and_rejects_target_season(self):
        history = pd.DataFrame(dict(
            Driver=['AAA', 'AAA', 'AAA', 'AAA', 'BBB', 'AAA'],
            Venue=['marina bay'] * 5 + ['monza'],
            Season=[2024, 2024, 2025, 2025, 2025, 2025],
            Session=['Q', 'R', 'Q', 'R', 'R', 'R'],
            QualiRatio=[1.00, np.nan, 1.02, np.nan, np.nan, np.nan],
            PaceRatio=[np.nan, 0.98, np.nan, 1.00, 1.03, 0.90]))
        frame = pd.DataFrame(dict(Driver=['AAA', 'BBB', 'CCC', 'AAA'], Year=2026,
                                  Venue=['marina bay', 'marina bay', 'marina bay', 'madrid']))
        actual = NS['add_venue_history'](frame, history)
        self.assertEqual(len(actual), 4)
        np.testing.assert_allclose(actual.VenuePace, [0.99, 1.03, np.nan, np.nan], equal_nan=True)
        np.testing.assert_allclose(actual.VenueQualiRatio, [1.01, np.nan, np.nan, np.nan], equal_nan=True)
        # Recomputing replaces rather than duplicates the columns.
        self.assertEqual(list(NS['add_venue_history'](actual, history).columns), list(actual.columns))
        with self.assertRaises(ValueError):
            NS['add_venue_history'](frame, history.assign(Season=[2024, 2024, 2025, 2025, 2025, 2026]))

    def test_missing_qualifying_keeps_entrant_and_target_loads_only_q(self):
        class Session:
            results = pd.DataFrame(dict(Abbreviation=['AAA', 'BBB'], FirstName=['A', 'B'],
                LastName=['One', 'Two'], TeamName=['X', 'Y'], Position=[1., np.nan],
                Q1=pd.to_timedelta([90, None], unit='s'),
                Q2=pd.to_timedelta([None, None]), Q3=pd.to_timedelta([None, None])))
            def load(self, **kwargs): pass
        session = Session()
        with patch.object(fastf1, 'get_session', return_value=session) as load:
            frame = NS['build_race_frame'](2026, 16, False)
            self.assertEqual(len(frame), 2)
            self.assertTrue(frame.MissingQualiTime.iloc[1])
            load.assert_called_once_with(2026, 16, 'Q')
            session.results['Q1'] = pd.to_timedelta([None, None])
            with self.assertRaises(ValueError): NS['get_quali_frame'](2026, 16)

    def test_empty_history_feature_is_imputed(self):
        x = pd.DataFrame(dict(QualiRatio=[1., 1.01, np.nan], QualifyingPosition=[1., 2., np.nan], PriorPace=[np.nan]*3))
        model = NS['make_model']().fit(x, [0.99, 1., 1.01])
        self.assertTrue(np.isfinite(model.predict(x)).all())

    def test_no_validation_folds(self):
        frame = pd.DataFrame(dict(RaceIndex=[0, 1, 2, 3], RaceId=list('abcd')))
        walk, scores = NS['validate'](frame)
        self.assertTrue(walk.empty)
        self.assertEqual(scores, {})

    def test_walk_forward_fits_only_earlier_races(self):
        rows = []
        for race in range(6):
            for driver in range(3):
                rows.append(dict(RaceId=str(race), Driver=str(driver), RaceIndex=race,
                    RaceStartUtc=pd.Timestamp('2026-01-01', tz='UTC') + pd.Timedelta(days=race),
                    QualiRatio=1 + driver / 100, QualifyingPosition=driver + 1,
                    PriorPace=1., PaceRatio=1 + driver / 200))
        frame = pd.DataFrame(rows)
        fits = []
        original = NS['make_model']
        class RecordingModel:
            def fit(self, x, y):
                fits.append(frame.loc[x.index, 'RaceIndex'].max())
                self.model = original().fit(x, y)
                return self
            def predict(self, x):
                self.assertion = frame.loc[x.index, 'RaceIndex'].min() > fits[-1]
                if not self.assertion:
                    raise AssertionError('Future race in training fold')
                return self.model.predict(x)
        with patch.dict(NS, make_model=RecordingModel):
            walk, _ = NS['validate'](frame)
        self.assertEqual(fits, [3, 4])
        self.assertEqual(walk.RaceId.unique().tolist(), ['4', '5'])

    def test_finishing_form_uses_only_earlier_races(self):
        frame = pd.DataFrame(dict(Driver=['A']*5, RaceStartUtc=pd.to_datetime(
            ['2026-03-05', '2026-03-01', '2026-03-02', '2026-03-03', '2026-03-04'], utc=True),
            FinishPosition=[9., 1., 2., 3., 20.], NotClassified=[False, False, False, False, True]))
        actual = NS['add_finishing_form'](frame)
        np.testing.assert_allclose(actual.PriorFinish, [np.nan, 1., 1.5, 2., 25 / 3], equal_nan=True)
        np.testing.assert_allclose(actual.PriorNotClassifiedRate, [np.nan, 0., 0., 0., .25], equal_nan=True)

    def test_rank_within_breaks_ties_by_driver(self):
        ranks = NS['rank_within']([2., 5., 5.], ['CCC', 'BBB', 'AAA'], higher_is_better=True)
        self.assertEqual(ranks.tolist(), [3, 2, 1])
        ranks = NS['rank_within']([2., 5., 5.], ['CCC', 'BBB', 'AAA'], higher_is_better=False)
        self.assertEqual(ranks.tolist(), [1, 3, 2])

    def test_finishing_validation_fits_only_earlier_races(self):
        rows = []
        for race in range(6):
            for driver in range(4):
                rows.append(dict(RaceId=str(race), Driver=str(driver), RaceIndex=race,
                    RaceStartUtc=pd.Timestamp('2026-01-01', tz='UTC') + pd.Timedelta(days=race),
                    QualiRatio=1 + driver / 100, QualifyingPosition=driver + 1, GridPosition=driver + 1,
                    PriorPace=1., PriorFinish=np.nan if race == 0 else driver + 1.,
                    PaceRatio=1 + driver / 200, FinishPosition=driver + 1.))
        frame = pd.DataFrame(rows)
        fits = []
        original = NS['make_ranker']
        class RecordingRanker:
            def fit(self, pool):
                fits.append(pool.num_row())
                self.model = original().fit(pool)
                return self
            def predict(self, x):
                return self.model.predict(x)
        with patch.dict(NS, make_ranker=RecordingRanker):
            walk, per_race, _ = NS['validate_finishing'](frame)
        self.assertEqual(fits, [16, 20])
        self.assertEqual(sorted(walk.RaceId.unique()), ['4', '5'])
        self.assertEqual(set(per_race.index.get_level_values('Method')), {'CatBoost', 'Grid order', 'Ridge pace'})
        np.testing.assert_allclose(per_race.xs('Grid order', level='Method')['Position MAE'], 0.)

    def test_no_finishing_validation_folds(self):
        frame = pd.DataFrame(dict(RaceIndex=[0, 1, 2, 3], RaceId=list('abcd')))
        walk, per_race, adopt = NS['validate_finishing'](frame)
        self.assertTrue(walk.empty and per_race.empty)
        self.assertFalse(adopt)


def podium_frame(races=6, drivers=8, seed=0):
    """Synthetic classified pool: finish order follows grid order plus noise; every third session is a sprint."""
    rng = np.random.default_rng(seed)
    rows = []
    for race in range(races):
        finish = (np.arange(drivers) + rng.normal(0, 2, drivers)).argsort().argsort() + 1
        kind, laps = ('sprint', 17) if race % 3 == 2 else ('race', 50)
        for driver in range(drivers):
            retired = bool(finish[driver] > drivers - 1)
            rows.append(dict(RaceId=str(race), Driver=f'D{driver}', Team=f'T{driver // 2}', Kind=kind, RaceIndex=race,
                RaceStartUtc=pd.Timestamp('2026-01-01', tz='UTC') + pd.Timedelta(days=race),
                QualiRatio=1 + driver / 100, QualifyingPosition=driver + 1., GridPosition=driver + 1.,
                PriorPace=1 + driver / 200, PriorFinish=np.nan if race == 0 else driver + 1.,
                PriorNotClassifiedRate=np.nan if race == 0 else 0.1,
                PaceRatio=1 + driver / 200 + rng.normal(0, .002), FinishPosition=float(finish[driver]),
                NotClassified=retired, LapsCompleted=laps // 2 if retired else laps, RaceLaps=laps,
                PitLossRatio=0.2, StopsPerDriver=0 if kind == 'sprint' else 1, DegPerLap=0.0004, SCPerLap=0.03))
    return pd.DataFrame(rows)


OUTCOME_COLUMNS = ['FinishPosition', 'PaceRatio', 'NotClassified', 'LapsCompleted', 'RaceLaps',
                   'PitLossRatio', 'StopsPerDriver', 'DegPerLap', 'SCPerLap']


def scramble_outcomes(current):
    """`current` with every outcome column replaced by nonsense."""
    scrambled = current.copy()
    scrambled['FinishPosition'] = scrambled.FinishPosition.to_numpy()[::-1]
    scrambled['PaceRatio'] = scrambled.PaceRatio.to_numpy()[::-1] + .5
    scrambled['NotClassified'] = ~scrambled.NotClassified
    for column in OUTCOME_COLUMNS[3:]:
        scrambled[column] = -99.
    return scrambled


class PodiumTests(unittest.TestCase):
    def test_podium_constants_match_notebook_config(self):
        config = next(c for c in NB['cells'] if c['cell_type'] == 'code' and 'PODIUM_METHODS' in ''.join(c['source']))
        values = {t.targets[0].id: ast.literal_eval(t.value) for t in ast.parse(''.join(config['source'])).body
                  if isinstance(t, ast.Assign) and isinstance(t.targets[0], ast.Name) and t.targets[0].id in ('PODIUM_METHODS', 'PROB_METHODS')}
        self.assertEqual(values, dict(PODIUM_METHODS=PODIUM_METHODS, PROB_METHODS=PROB_METHODS))

    def test_new_models_fit_only_on_earlier_races(self):
        frame = podium_frame()
        fits, sim_sizes, held_out = [], [], []
        fold = NS['podium_fold']
        def recording_fold(past, current):
            held_out.append(current.RaceIndex.min())
            return fold(past, current)
        def recording(factory):
            class Recorder:
                def fit(self, x, y):
                    latest = frame.loc[x.index, 'RaceIndex'].max()
                    if latest >= held_out[-1]:
                        raise AssertionError('Held-out or later race in training fold')
                    fits.append(factory.__name__)
                    self.model = factory().fit(x, y)
                    return self
                def predict_proba(self, x):
                    return self.model.predict_proba(x)
            return Recorder
        simulations = {name: NS[name] for name in ('simulate_race', 'simulate_laps')}
        def recording_sim(name):
            def run(pace, *args, **kwargs):
                residuals = args[1] if name == 'simulate_race' else args[2]
                sim_sizes.append((name, len(residuals)))
                return simulations[name](pace, *args, **kwargs)
            return run
        with patch.dict(NS, podium_fold=recording_fold, make_podium_logit=recording(NS['make_podium_logit']),
                        make_podium_tree=recording(NS['make_podium_tree']),
                        simulate_race=recording_sim('simulate_race'), simulate_laps=recording_sim('simulate_laps')):
            walk = NS['validate_podium'](frame)
        self.assertEqual(sorted(walk.RaceId.unique()), ['4', '5'])
        self.assertEqual(held_out, [4, 5])
        # Per fold: the plain models, then each calibrated model's inner folds and its refit.
        per_fold = ['make_podium_logit', 'make_podium_tree'] + ['make_podium_logit'] * 5 + ['make_podium_tree'] * 5
        self.assertEqual(fits, per_fold * 2)
        # Residuals come from earlier races only.
        self.assertEqual(sim_sizes, [('simulate_race', 32), ('simulate_laps', 32),
                                     ('simulate_race', 40), ('simulate_laps', 40)])

    def test_models_never_read_current_race_outcomes(self):
        frame = podium_frame()
        past, current = frame[frame.RaceIndex < 5], frame[frame.RaceIndex == 5].copy()
        pd.testing.assert_frame_equal(NS['podium_fold'](past, current), NS['podium_fold'](past, scramble_outcomes(current)))

    def test_fold_probabilities_are_valid(self):
        frame = podium_frame()
        fold = NS['podium_fold'](frame[frame.RaceIndex < 5], frame[frame.RaceIndex == 5])
        for method in PROB_METHODS:
            p = fold[f'{method} P(podium)']
            self.assertTrue(p.between(0, 1).all(), method)
        for column in ['Simulation P(win)', 'Grid-slot rate P(win)']:
            self.assertTrue(fold[column].between(0, 1).all(), column)
        self.assertAlmostEqual(fold['Simulation P(win)'].sum(), 1.)
        self.assertAlmostEqual(fold['Simulation P(podium)'].sum(), 3.)
        self.assertEqual(sorted(fold['Simulation expected position'].round(6).between(1, 8).unique()), [True])

    def test_simulation_probabilities_and_retirements(self):
        pace = [1., 1.001, 1.002, 1.003, 1.004]
        residuals = np.random.default_rng(1).normal(0, .002, 100)
        sim = NS['simulate_race'](pace, [0.] * 5, residuals, n_sims=2000, seed=3)
        self.assertAlmostEqual(sim['P(win)'].sum(), 1.)
        self.assertAlmostEqual(sim['P(podium)'].sum(), 3.)
        self.assertTrue(sim[['P(win)', 'P(podium)']].stack().between(0, 1).all())
        self.assertGreater(sim['P(win)'][0], sim['P(win)'][4])
        pd.testing.assert_frame_equal(sim, NS['simulate_race'](pace, [0.] * 5, residuals, n_sims=2000, seed=3))
        retiring = NS['simulate_race'](pace, [1., 0., 0., 0., 0.], residuals, n_sims=2000, seed=3)
        self.assertEqual(retiring['P(win)'][0], 0.)
        self.assertEqual(retiring['P(podium)'][0], 0.)
        self.assertEqual(retiring['Expected position'][0], 5.)
        with self.assertRaises(ValueError):
            NS['simulate_race']([np.nan, 1.], [0., 0.], residuals, n_sims=10)

    def test_retirement_rate_is_pulled_toward_field(self):
        past = pd.DataFrame(dict(Driver=['A'] * 10 + ['B'] + ['C'] * 10, NotClassified=[False] * 10 + [False] + [True] * 10))
        current = pd.DataFrame(dict(Driver=['A', 'B', 'C', 'D'], PriorNotClassifiedRate=[0., 0., 1., np.nan]))
        field = past.NotClassified.mean()
        p = NS['dnf_probabilities'](past, current)
        self.assertAlmostEqual(p[3], field)                  # no history: field average
        self.assertAlmostEqual(p[1], 5 * field / 6)          # one clean race barely moves it
        self.assertLess(p[0], p[1])                          # ten clean races move it further
        self.assertGreater(p[2], field)
        self.assertTrue(((p > 0) & (p < 1)).all())

    def test_grid_slot_rates_smooth_and_follow_history(self):
        past = pd.DataFrame(dict(GridPosition=[1., 1., 2., 8., 8., 9.], FinishPosition=[1., 2., 3., 9., 10., 8.]))
        rates = NS['grid_slot_rates'](past, np.array([1., 8., 20.]))
        self.assertGreater(rates['podium'][0], rates['podium'][1])
        self.assertTrue(((rates['podium'] > 0) & (rates['podium'] < 1)).all())
        self.assertGreater(rates['win'][0], 0.)

    def test_podium_validation_matches_finishing_validation(self):
        frame = podium_frame()
        podium = NS['validate_podium'](frame)
        finish, _, _ = NS['validate_finishing'](frame)
        shared = podium.merge(finish, on=['RaceId', 'Driver'], suffixes=('', '_finish'), validate='one_to_one')
        self.assertEqual(len(shared), len(podium))
        self.assertEqual(len(podium), len(finish))
        for column in ['Actual', 'Grid order', 'Ridge pace', 'CatBoost']:
            np.testing.assert_array_equal(shared[column], shared[f'{column}_finish'], column)

    def test_no_podium_validation_folds(self):
        frame = pd.DataFrame(dict(RaceIndex=[0, 1, 2, 3], RaceId=list('abcd')))
        walk = NS['validate_podium'](frame)
        self.assertTrue(walk.empty)
        self.assertTrue(all(t.empty for t in NS['evaluate_podium'](walk)))

    @patch.dict(NS, PODIUM_METHODS=PODIUM_METHODS[:9], PROB_METHODS=PROB_METHODS[:4])
    def test_podium_scores_hits_and_probability_metrics(self):
        walk = podium_frame(races=1, drivers=6)[['RaceId', 'Driver']].copy()
        walk['Actual'] = np.arange(1, 7)
        for method in PODIUM_METHODS[:9]:
            walk[method] = np.arange(1, 7)
        walk['Ridge pace'] = [2, 1, 3, 4, 5, 6]
        walk['Logistic P(podium)'] = [1., 1., 1., 0., 0., 0.]
        walk['Shallow tree P(podium)'] = .5
        walk['Simulation P(podium)'] = [0., 0., 0., 1., 1., 1.]
        walk['Grid-slot rate P(podium)'] = [.9, .8, .7, .1, .1, .1]
        per_race = NS['podium_scores'](walk).loc['0']
        self.assertEqual(per_race.loc['Grid order', ['Podium overlap', 'Winner correct', 'Exact order']].tolist(), [1., 1., 1.])
        self.assertEqual(per_race.loc['Ridge pace', ['Podium overlap', 'Winner correct', 'Exact order']].tolist(), [1., 0., 0.])
        self.assertTrue(np.isnan(per_race.loc['Grid order', 'Brier']))
        self.assertEqual(per_race.loc['Logistic', 'Brier'], 0.)
        self.assertAlmostEqual(per_race.loc['Shallow tree', 'Brier'], .25)
        self.assertAlmostEqual(per_race.loc['Shallow tree', 'Log loss'], np.log(2))
        self.assertEqual(per_race.loc['Simulation', 'Brier'], 1.)
        self.assertAlmostEqual(per_race.loc['Simulation', 'Log loss'], -np.log(1e-3))  # clipped, finite
        walk['Logistic'] = np.arange(1, 7)
        table = NS['calibration_table'](walk)
        self.assertEqual(table.loc['Shallow tree', 'Driver-races'].sum(), 6)
        self.assertAlmostEqual(table.loc['Logistic'].iloc[-1]['Actual rate'], 1.)

    def test_bootstrap_interval_must_exclude_zero(self):
        index = pd.MultiIndex.from_product([list('abcdefgh'), ['Ridge pace', 'Other']], names=['RaceId', 'Method'])
        same = pd.Series(.5, index=index)
        stats = NS['bootstrap_difference'](same, 'Other', 'Ridge pace')
        self.assertEqual((stats['diff'], stats['lo'], stats['hi']), (0., 0., 0.))
        better = same.copy()
        better.loc[(slice(None), 'Other')] = [.5, .75] * 4
        stats = NS['bootstrap_difference'](better, 'Other', 'Ridge pace')
        self.assertGreater(stats['lo'], 0.)
        noisy = pd.Series([.5, .5, 1., 0., .5, .5, 0., 1., .5, .5, 1., 0.] * 1 + [.5, .5, 0., 1.], index=index)
        stats = NS['bootstrap_difference'](noisy, 'Other', 'Ridge pace')
        self.assertLess(stats['lo'], 0.); self.assertGreater(stats['hi'], 0.)


def pace_frame(races=7, drivers=6, seed=1):
    """Synthetic labelled pool for the pace-model comparison, with form features built by the notebook."""
    rng = np.random.default_rng(seed)
    rows = []
    for race in range(races):
        for driver in range(drivers):
            rows.append(dict(RaceId=str(race), Driver=f'D{driver}', Team=f'T{driver // 2}', Kind='race',
                RaceStartUtc=pd.Timestamp('2026-01-01', tz='UTC') + pd.Timedelta(days=race),
                QualiRatio=1 + driver / 100 + rng.normal(0, .002), QualifyingPosition=driver + 1.,
                PaceRatio=1 + driver / 200 + rng.normal(0, .002)))
    return NS['add_prior_form'](pd.DataFrame(rows))


class ModelComparisonTests(unittest.TestCase):
    def test_race_conditions_from_laps(self):
        rows = []
        for driver, base in (('AAA', 100.), ('BBB', 101.)):
            for lap in range(1, 11):
                status = '4' if lap in (4, 5) else '1'
                seconds = base + 0.1 * (lap - 1 if lap <= 6 else lap - 7) + (5. if lap == 1 else 0.)
                rows.append(dict(Driver=driver, LapNumber=float(lap), Stint=1. if lap <= 6 else 2.,
                                 TyreLife=float(lap if lap <= 6 else lap - 6), TrackStatus=status,
                                 LapTime=pd.Timedelta(seconds=seconds + (12. if lap in (6, 7) else 0.)),
                                 PitInTime=pd.Timedelta(seconds=1) if lap == 6 else pd.NaT,
                                 PitOutTime=pd.Timedelta(seconds=1) if lap == 7 else pd.NaT))
        conditions = NS['race_conditions'](pd.DataFrame(rows))
        self.assertEqual(conditions['RaceLaps'], 10)
        self.assertEqual(conditions['StopsPerDriver'], 1)
        self.assertAlmostEqual(conditions['SCPerLap'], 0.1)       # one deployment over laps 4-5
        self.assertGreater(conditions['DegPerLap'], 0)             # laps get slower on older tyres
        self.assertGreater(conditions['PitLossRatio'], 0.2)        # 24 s lost on a ~100 s lap
        self.assertLess(conditions['PitLossRatio'], 0.3)
        # Columns FastF1 did not supply give NaN rather than an error.
        bare = NS['race_conditions'](pd.DataFrame(rows)[['Driver', 'LapTime', 'PitInTime', 'PitOutTime']])
        self.assertTrue(all(np.isnan(v) for v in bare.values()))

    def test_target_frame_has_no_race_conditions(self):
        session = SimpleNamespace(results=quali_results(), load=lambda **kwargs: None)
        with patch.object(fastf1, 'get_session', return_value=session):
            frame = NS['build_race_frame'](2026, 17, False, kind='sprint')
        for column in OUTCOME_COLUMNS:
            self.assertTrue(frame[column].isna().all(), column)

    def test_kalman_and_ewm_form_use_only_earlier_sessions(self):
        forecasts = NS['kalman_forecast']([1.02, np.nan, 1.02, 0.95])
        self.assertEqual(forecasts[0], 1.0)                       # field median before any session
        self.assertEqual(forecasts[1], forecasts[2])              # a missing session adds drift only
        self.assertGreater(forecasts[3], forecasts[1])            # two slow sessions move it further
        np.testing.assert_array_equal(forecasts[:3], NS['kalman_forecast']([1.02, np.nan, 1.02, 2.0])[:3])
        frame = pace_frame()
        changed = frame.copy()
        last = changed.RaceIndex == changed.RaceIndex.max()
        changed.loc[last, 'PaceRatio'] = 5.
        changed = NS['add_prior_form'](changed.drop(columns=['PriorPace', 'EwmPace', 'KalmanPace']))
        for column in ('PriorPace', 'EwmPace', 'KalmanPace'):
            np.testing.assert_allclose(changed[column], frame[column], equal_nan=True, err_msg=column)
        self.assertTrue(frame.loc[frame.RaceIndex == 0, 'EwmPace'].isna().all())

    def test_plackett_luce_and_bradley_terry_learn_the_order(self):
        frame = podium_frame(races=8)
        x = frame[['QualiRatio', 'GridPosition']]
        retired = frame.NotClassified
        for model in (NS['PlackettLuce']().fit(x, frame.FinishPosition, retired, frame.RaceIndex),
                      NS['BradleyTerry']().fit(x, frame.FinishPosition, retired, frame.RaceIndex)):
            scores = model.predict(x.iloc[:8])
            self.assertGreater(pd.Series(scores).corr(pd.Series(-np.arange(8.)), method='spearman'), 0.9)
        probabilities = NS['PlackettLuce']().fit(x, frame.FinishPosition, retired, frame.RaceIndex) \
            .probabilities(x.iloc[:8], n_sims=2000, seed=0)
        self.assertAlmostEqual(probabilities['P(win)'].sum(), 1.)
        self.assertAlmostEqual(probabilities['P(podium)'].sum(), 3.)
        self.assertGreater(probabilities['P(win)'][0], probabilities['P(win)'][7])

    def test_ordinal_logit_probabilities(self):
        frame = podium_frame(races=8)
        model = NS['OrdinalLogit']().fit(frame[['QualiRatio', 'GridPosition']], frame.FinishPosition)
        p = model.probabilities(frame[['QualiRatio', 'GridPosition']].iloc[:8])
        self.assertTrue(p.stack().between(0, 1).all())
        self.assertTrue((p['P(win)'] <= p['P(podium)']).all())
        self.assertGreater(p['P(podium)'][0], p['P(podium)'][7])

    def test_ratings_follow_results_in_date_order(self):
        rows = []
        for race in range(4):
            for driver, place in (('FAST', 1.), ('MID', 2.), ('SLOW', 3.)):
                rows.append(dict(RaceIndex=race, Driver=driver, FinishPosition=place))
        past = pd.DataFrame(rows).sample(frac=1, random_state=0)  # row order must not matter
        for ratings in (NS['elo_ratings'](past), NS['glicko2_ratings'](past), NS['trueskill_ratings'](past)):
            self.assertGreater(ratings['FAST'], ratings['MID'])
            self.assertGreater(ratings['MID'], ratings['SLOW'])
            self.assertNotIn('NEW', ratings)
        # The comeback counts only if it is the latest race.
        late = pd.concat([past, pd.DataFrame(dict(RaceIndex=[4] * 3, Driver=['SLOW', 'MID', 'FAST'],
                                                  FinishPosition=[1., 2., 3.]))])
        self.assertLess(NS['elo_ratings'](late)['FAST'] - NS['elo_ratings'](late)['SLOW'],
                        NS['elo_ratings'](past)['FAST'] - NS['elo_ratings'](past)['SLOW'])

    def test_glicko2_volatility_matches_glickman_example(self):
        # Glickman (2013), "Example of the Glicko-2 system": sigma' = 0.05999.
        sigma = NS['glicko2_volatility'](phi=1.1513, sigma=0.06, v=1.7785, delta=-0.4834)
        self.assertAlmostEqual(sigma, 0.05999, delta=1e-5)

    def test_hazard_scales_with_distance_and_shrinks_to_team(self):
        past = pd.DataFrame(dict(Driver=['A', 'B', 'C', 'D'] * 5, Team=['X', 'X', 'Y', 'Y'] * 5, Kind='race',
                                 NotClassified=[True, False, False, False] + [False] * 16,
                                 LapsCompleted=[10, 50, 50, 50] + [50] * 16, RaceLaps=50))
        race = pd.DataFrame(dict(Driver=['A', 'B', 'C', 'E'], Team=['X', 'X', 'Y', 'Z'], Kind='race'))
        p = NS['hazard_dnf_probabilities'](past, race)
        self.assertTrue(((p > 0) & (p < 1)).all())
        self.assertGreater(p[0], p[1])        # A retired; B shares A's team
        self.assertGreater(p[1], p[2])        # team X has the retirement
        sprint = NS['hazard_dnf_probabilities'](past, race.assign(Kind='sprint'))
        self.assertTrue((sprint < p).all())   # a third of the distance
        np.testing.assert_allclose(-np.log(1 - sprint), -np.log(1 - p) / 3)

    def test_retirement_validation_scores_both_models(self):
        table = NS['validate_retirements'](podium_frame())
        self.assertEqual(sorted(table.index.get_level_values('RaceId').unique()), ['4', '5'])
        self.assertEqual(set(table.index.get_level_values('Method')), {'Shrunk rate', 'Hazard'})
        self.assertTrue(NS['validate_retirements'](podium_frame(races=4)).empty)

    def test_race_setup_uses_same_kind_and_defaults(self):
        frame = podium_frame()
        self.assertEqual(NS['race_setup'](frame, 'sprint')['RaceLaps'], 17)
        self.assertEqual(NS['race_setup'](frame, 'race')['StopsPerDriver'], 1)
        missing = NS['race_setup'](frame.drop(columns=['SCPerLap']).assign(DegPerLap=np.nan), 'race')
        self.assertEqual(missing['SCPerLap'], NS['LAPSIM_DEFAULTS']['race']['SCPerLap'])
        self.assertEqual(missing['DegPerLap'], NS['LAPSIM_DEFAULTS']['race']['DegPerLap'])

    def test_lap_simulation_probabilities_and_passing(self):
        setup = dict(RaceLaps=20, PitLossRatio=0.2, StopsPerDriver=1, DegPerLap=0.0005, SCPerLap=0.05)
        pace, residuals = [1., 1.001, 1.002, 1.003], np.zeros(10)
        sim = NS['simulate_laps'](pace, [1, 2, 3, 4], [0.] * 4, residuals, setup, n_sims=400, seed=1)
        self.assertAlmostEqual(sim['P(win)'].sum(), 1.)
        self.assertAlmostEqual(sim['P(podium)'].sum(), 3.)
        self.assertGreater(sim['P(win)'][0], sim['P(win)'][3])
        pd.testing.assert_frame_equal(sim, NS['simulate_laps'](pace, [1, 2, 3, 4], [0.] * 4, residuals, setup,
                                                               n_sims=400, seed=1))
        retiring = NS['simulate_laps'](pace, [1, 2, 3, 4], [1., 0., 0., 0.], residuals, setup, n_sims=200, seed=1)
        self.assertEqual(retiring['P(podium)'][0], 0.)
        # Without noise, a slightly faster car starting last cannot clear the pass margin.
        quiet = dict(setup, StopsPerDriver=0, DegPerLap=0., SCPerLap=0.)
        with patch.dict(NS, LAPSIM_LAP_NOISE=0.):
            stuck = NS['simulate_laps']([1.001, 1.], [1, 2], [0., 0.], residuals, quiet, n_sims=50, seed=1)
            self.assertEqual(stuck['P(win)'].tolist(), [1., 0.])
            passing = NS['simulate_laps']([1.02, 1.], [1, 2], [0., 0.], residuals, quiet, n_sims=50, seed=1)
            self.assertEqual(passing['P(win)'].tolist(), [0., 1.])
        with self.assertRaises(ValueError):
            NS['simulate_laps']([np.nan, 1.], [1, 2], [0., 0.], residuals, setup, n_sims=10)

    def test_calibrated_classifier_folds_never_split_a_race(self):
        frame = podium_frame()
        folds = NS['race_folds'](frame.RaceIndex)
        self.assertEqual(len(folds), 4)
        for fit_rows, check_rows in folds:
            self.assertFalse(set(frame.RaceIndex.iloc[fit_rows]) & set(frame.RaceIndex.iloc[check_rows]))
        model = NS['RaceCalibrated'](NS['make_podium_logit']).fit(
            frame[['QualiRatio', 'GridPosition']], (frame.FinishPosition <= 3).astype(int), frame.RaceIndex)
        p = model.predict_proba(frame[['QualiRatio', 'GridPosition']])
        self.assertTrue(((p >= 0) & (p <= 1)).all())
        np.testing.assert_allclose(p.sum(axis=1), 1.)

    def test_fold_ensembles_combine_the_other_methods(self):
        frame = podium_frame()
        fold = NS['podium_fold'](frame[frame.RaceIndex < 5], frame[frame.RaceIndex == 5])
        single = [m for m in PROB_METHODS if m != 'Probability average']
        np.testing.assert_allclose(fold['Probability average P(podium)'],
                                   fold[[f'{m} P(podium)' for m in single]].mean(axis=1))
        for method in PODIUM_METHODS:
            self.assertEqual(sorted(fold[method]), list(range(1, 9)), method)

    def test_pace_models_never_read_current_outcomes(self):
        frame = pace_frame()
        past, current = frame[frame.RaceIndex < 6], frame[frame.RaceIndex == 6]
        scrambled = current.assign(PaceRatio=current.PaceRatio.to_numpy()[::-1] + .5)
        fold = NS['pace_model_fold'](past, current)
        pd.testing.assert_frame_equal(fold, NS['pace_model_fold'](past, scrambled))
        self.assertEqual([c for c in fold.columns if c in NS['PACE_MODELS']], NS['PACE_MODELS'])
        self.assertTrue(np.isfinite(fold[NS['PACE_MODELS']].to_numpy()).all())
        for name in ('Bayesian ridge', 'Quantile', 'Gaussian process'):
            self.assertTrue((fold[f'{name} low'] <= fold[f'{name} high']).all(), name)

    def test_mixed_effects_handles_unseen_driver_and_team(self):
        frame = pace_frame()
        model = NS['make_pace_model']('Mixed effects').fit(frame)
        rookie = frame.iloc[:2].assign(Driver=['NEW', 'D0'], Team=['NEWTEAM', 'T0'])
        predictions = model.predict(rookie)
        self.assertTrue(np.isfinite(predictions).all())
        self.assertNotEqual(predictions[0], predictions[1])

    def test_pace_comparison_matches_validation_folds(self):
        frame = pace_frame()
        walk, _ = NS['validate'](frame, verbose=False)
        with patch.dict(NS, PACE_MODELS=['Ridge', 'Kalman form only', 'Mean of models']):
            pace_walk = NS['validate_pace_models'](frame)
            per_race = NS['pace_model_scores'](pace_walk)
            summary = NS['pace_model_summary'](pace_walk, per_race)
            boot = NS['pace_bootstrap'](per_race)
        self.assertEqual(pace_walk.RaceId.unique().tolist(), walk.RaceId.unique().tolist())
        np.testing.assert_allclose(pace_walk['Ridge'], walk['Predicted'])
        self.assertAlmostEqual(summary.loc['Ridge', 'Pace MAE'], mean_absolute_error(walk.Actual, walk.Predicted))
        self.assertEqual(sorted(boot.Method.unique()), ['Kalman form only', 'Mean of models'])
        self.assertTrue(NS['validate_pace_models'](pace_frame(races=4)).empty)


if __name__ == '__main__': unittest.main()
