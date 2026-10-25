"""Offline tests for scoring saved predictions against actual results."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

import score_predictions as sp


def classification(*codes):
    return [dict(position=i, code=c, name=f'Driver {c.title()}', status='Finished') for i, c in enumerate(codes, 1)]


class ParsePredictionTest(unittest.TestCase):
    def test_reads_session_best_answer_and_models_from_both_snapshots(self):
        race = sp.parse_prediction(sp.RESULTS / 'podium_prediction_2026-10-04.md')
        sprint = sp.parse_prediction(sp.RESULTS / 'sprint_prediction_2026-10-10.md')
        self.assertEqual((race['event'], race['kind'], race['date']), ('Bahrain Grand Prix', 'race', '2026-10-04'))
        self.assertEqual((sprint['event'], sprint['kind'], sprint['date']), ('Singapore Grand Prix', 'sprint', '2026-10-10'))
        self.assertEqual(race['best'], ['Verstappen', 'Hamilton', 'Antonelli'])
        self.assertEqual(race['models']['Logistic'], ['VER', 'HAM', 'ANT'])
        self.assertEqual(sprint['models']['CatBoost'], ['VER', 'RUS', 'PIA'])
        self.assertEqual(len(sprint['models']), 9)
        self.assertEqual(sp.actual_path(sprint).name, '2026-singapore-grand-prix-sprint.json')

    def test_rejects_a_model_row_without_driver_codes(self):
        text = (sp.RESULTS / 'podium_prediction_2026-10-04.md').read_text().replace('| CatBoost | HAM |', '| CatBoost | — |')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'podium_prediction_x.md'
            path.write_text(text)
            with self.assertRaisesRegex(ValueError, 'CatBoost'):
                sp.parse_prediction(path)

    def test_rejects_a_snapshot_without_a_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'podium_prediction_x.md'
            path.write_text('# Something else\n')
            with self.assertRaisesRegex(ValueError, 'title'):
                sp.parse_prediction(path)


class ScoreTest(unittest.TestCase):
    def test_counts_places_exact_positions_and_winner(self):
        actual = dict(classification=classification('VER', 'ANT', 'HAM', 'LEC', 'RUS'))
        result = sp.score(['VER', 'HAM', 'LEC'], actual)
        self.assertEqual(result['podium'], ['VER', 'ANT', 'HAM'])
        self.assertEqual((result['places'], result['exact'], result['winner']), (2, 1, True))
        self.assertEqual(result['misses'], [('LEC', 'P4')])

    def test_unclassified_drivers_are_never_on_the_podium(self):
        rows = classification('HAM', 'LEC', 'ANT') + [dict(position=None, code='RUS', name='George Russell', status='DNF')]
        actual = dict(classification=[rows[-1], *rows[:-1]])
        result = sp.score(['RUS', 'HAM', 'LEC'], actual)
        self.assertEqual(result['podium'], ['HAM', 'LEC', 'ANT'])
        self.assertEqual(result['misses'], [('RUS', 'DNF')])
        self.assertFalse(result['winner'])

    def test_needs_three_classified_finishers(self):
        rows = [dict(position=None, code=c, name=c, status='DNF') for c in ('VER', 'HAM', 'LEC')]
        with self.assertRaisesRegex(ValueError, 'three classified'):
            sp.score(['VER', 'HAM', 'LEC'], dict(event='Test Grand Prix', classification=rows))

    def test_best_answer_surnames_map_to_codes(self):
        actual = dict(classification=[dict(position=1, code='VER', name='Max Verstappen', status='Finished'),
                                      dict(position=2, code='PER', name='Sergio Pérez', status='Finished')])
        self.assertEqual(sp.surname_codes(actual, ['Verstappen', 'Perez']), ['VER', 'PER'])
        with self.assertRaisesRegex(ValueError, 'Norris'):
            sp.surname_codes(actual, ['Norris'])

    def test_a_shared_surname_is_ambiguous(self):
        actual = dict(classification=[dict(position=1, code='MSC', name='Mick Schumacher', status='Finished'),
                                      dict(position=2, code='RSC', name='Ralf Schumacher', status='Finished')])
        with self.assertRaisesRegex(ValueError, 'shared'):
            sp.surname_codes(actual, ['Schumacher'])


class ScorecardTest(unittest.TestCase):
    def test_committed_scorecard_is_up_to_date(self):
        self.assertEqual(sp.SCORECARD.read_text(), sp.render(*sp.score_all(fetch=False)),
                         'results/scorecard.md is stale; run python score_predictions.py')

    def test_a_snapshot_without_a_result_is_listed_as_not_scored(self):
        text = (sp.RESULTS / 'podium_prediction_2026-10-04.md').read_text().replace(
            '2026 Bahrain Grand Prix (Sepang, Oct 4)', '2026 United States Grand Prix (Austin, Oct 25)')
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            for name in ('podium_prediction_2026-10-04.md', 'sprint_prediction_2026-10-10.md'):
                (results / name).write_text((sp.RESULTS / name).read_text())
            (results / 'podium_prediction_2026-10-25.md').write_text(text)
            with patch.object(sp, 'RESULTS', results), patch.object(sp, 'fetch_fastf1') as fetch:
                sessions, pending = sp.score_all(fetch=False)
        fetch.assert_not_called()
        self.assertEqual([s['pred']['label'] for s in sessions], ['2026 Bahrain Grand Prix', '2026 Singapore Sprint'])
        self.assertEqual([p['label'] for p in pending], ['2026 United States Grand Prix'])
        self.assertIn('## Not scored yet', sp.render(sessions, pending))

    def test_saved_results_round_trip(self):
        for path in sp.ACTUAL_DIR.glob('*.json'):
            self.assertEqual(sp.dump_actual(json.loads(path.read_text())), path.read_text(), path.name)


class LoadActualTest(unittest.TestCase):
    PRED = dict(year=2026, event='Bahrain Grand Prix', kind='race', date='2026-10-04', label='2026 Bahrain Grand Prix')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.multiple(sp, ACTUAL_DIR=Path(self.tmp.name) / 'actual', ROOT=Path(self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def fetched(self):
        return dict(year=2026, event='Bahrain Grand Prix', kind='race', date='2026-10-04', source='FastF1 test',
                    retrieved='2026-10-17', classification=classification('VER', 'ANT', 'HAM'))

    def test_fetches_through_fastf1_and_saves_when_no_file_exists(self):
        with patch.object(sp, 'fetch_fastf1', return_value=self.fetched()) as fetch:
            actual = sp.load_actual(self.PRED)
            self.assertEqual(sp.load_actual(self.PRED), actual)
        fetch.assert_called_once()
        self.assertTrue(sp.actual_path(self.PRED).exists())

    def test_explains_how_to_add_a_result_when_fastf1_fails(self):
        with patch.object(sp, 'fetch_fastf1', side_effect=ValueError('no results')), patch('builtins.print') as say:
            self.assertIsNone(sp.load_actual(self.PRED))
        self.assertIn('formula1.com', say.call_args.args[0])

    def test_does_not_fetch_before_the_session(self):
        with patch.object(sp, 'utc_today', return_value=sp.date(2026, 10, 3)), patch.object(sp, 'fetch_fastf1') as fetch:
            self.assertIsNone(sp.load_actual(self.PRED))
        fetch.assert_not_called()

    def test_refresh_keeps_the_saved_file_when_fastf1_fails(self):
        sp.ACTUAL_DIR.mkdir()
        sp.actual_path(self.PRED).write_text(sp.dump_actual(self.fetched()))
        with patch.object(sp, 'fetch_fastf1', side_effect=ValueError('blocked')) as fetch, patch('builtins.print'):
            self.assertEqual(sp.load_actual(self.PRED, refresh=True)['source'], 'FastF1 test')
        self.assertTrue(fetch.call_args.kwargs['renew'])

    def test_rejects_a_saved_result_for_another_session(self):
        sp.ACTUAL_DIR.mkdir()
        sp.actual_path(self.PRED).write_text(sp.dump_actual(dict(self.fetched(), date='2026-04-12')))
        with self.assertRaisesRegex(ValueError, 'date'):
            sp.load_actual(self.PRED)


class FetchFastF1Test(unittest.TestCase):
    def fake_fastf1(self, session_date, results):
        session = SimpleNamespace(date=pd.Timestamp(session_date), results=results, load=lambda **_: None)
        return SimpleNamespace(__version__='test', Cache=SimpleNamespace(enable_cache=lambda *_, **__: None),
                               get_session=lambda *_: session)

    def test_maps_classification_and_retirements(self):
        results = pd.DataFrame(dict(
            Position=[1.0, 2.0, 3.0, 4.0], ClassifiedPosition=['1', '2', '3', 'R'],
            Abbreviation=['VER', 'ANT', 'RUS', 'ALB'], FullName=['Max Verstappen', 'Kimi Antonelli', 'George Russell', 'Alexander Albon'],
            Status=['Finished', '+1 Lap', 'Retired', 'Retired']))
        with tempfile.TemporaryDirectory() as tmp, patch.object(sp, 'CACHE_DIR', Path(tmp) / 'cache'), \
                patch.dict(sys.modules, fastf1=self.fake_fastf1('2026-10-04 07:00', results)):
            actual = sp.fetch_fastf1(LoadActualTest.PRED)
        self.assertEqual([(r['position'], r['code'], r['status']) for r in actual['classification']],
                         [(1, 'VER', 'Finished'), (2, 'ANT', 'Finished'), (3, 'RUS', 'DNF'), (None, 'ALB', 'DNF')])

    def test_accepts_a_utc_date_a_day_after_the_local_date(self):
        results = pd.DataFrame(dict(
            Position=[1.0, 2.0, 3.0], ClassifiedPosition=['1', '2', '3'], Abbreviation=['VER', 'ANT', 'HAM'],
            FullName=['Max Verstappen', 'Kimi Antonelli', 'Lewis Hamilton'], Status=['Finished'] * 3))
        with tempfile.TemporaryDirectory() as tmp, patch.object(sp, 'CACHE_DIR', Path(tmp) / 'cache'), \
                patch.dict(sys.modules, fastf1=self.fake_fastf1('2026-10-05 04:00', results)):
            self.assertEqual(len(sp.fetch_fastf1(LoadActualTest.PRED)['classification']), 3)

    def test_rejects_results_without_a_classified_podium(self):
        results = pd.DataFrame(dict(
            Position=[1.0, 2.0, 3.0], ClassifiedPosition=['', '', ''], Abbreviation=['VER', 'ANT', 'HAM'],
            FullName=['Max Verstappen', 'Kimi Antonelli', 'Lewis Hamilton'], Status=[''] * 3))
        with tempfile.TemporaryDirectory() as tmp, patch.object(sp, 'CACHE_DIR', Path(tmp) / 'cache'), \
                patch.dict(sys.modules, fastf1=self.fake_fastf1('2026-10-04 07:00', results)):
            with self.assertRaisesRegex(ValueError, 'positions 1 to 3'):
                sp.fetch_fastf1(LoadActualTest.PRED)

    def test_rejects_a_session_on_another_date(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(sp, 'CACHE_DIR', Path(tmp) / 'cache'), \
                patch.dict(sys.modules, fastf1=self.fake_fastf1('2026-04-12 15:00', pd.DataFrame())):
            with self.assertRaisesRegex(ValueError, '2026-04-12'):
                sp.fetch_fastf1(LoadActualTest.PRED)


if __name__ == '__main__':
    unittest.main()
