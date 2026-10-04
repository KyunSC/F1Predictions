"""Offline regression checks for notebook forecasting boundaries."""
import ast
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import fastf1
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

NB = json.loads((Path(__file__).resolve().parents[1] / 'f1_race_prediction.ipynb').read_text())
NS = dict(fastf1=fastf1, np=np, pd=pd, SimpleImputer=SimpleImputer,
          Ridge=Ridge, make_pipeline=make_pipeline, StandardScaler=StandardScaler,
          FEATURES=['QualiRatio', 'QualifyingPosition', 'PriorPace'],
          TARGET_COL='PaceRatio', MIN_TRAIN_RACES=4)
NS['mean_absolute_error'] = mean_absolute_error
for cell in NB['cells']:
    if cell['cell_type'] == 'code':
        tree = ast.parse(''.join(cell['source']))
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<notebook>', 'exec'), NS)


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


if __name__ == '__main__': unittest.main()
