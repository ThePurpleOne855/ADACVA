from fractions import Fraction as F
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import contextlib
import io

from ada_piano.music_sheet import Exercise, ScoreEvent, ScoreNote, load_exercise
from ada_piano.ai_tutor import Tutor
from ada_piano.sound_sensor import NoteEvent, event_from_message, simulated_chords, midi_notes
from ada_piano.cli import main


def n(pitch, duration=1, extra='', voice='1', staff='1'):
    step, octave = pitch
    return f'<note>{extra}<pitch><step>{step}</step><octave>{octave}</octave></pitch><duration>{duration}</duration><voice>{voice}</voice><staff>{staff}</staff></note>'


def xml(*bars):
    measures=''.join(f'<measure number="{i}">{bar}</measure>' for i,bar in enumerate(bars,1))
    return '<score-partwise><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list><part id="P1">'+measures+'</part></score-partwise>'


def exercise(*groups):
    events=tuple(ScoreEvent(F(i), tuple(ScoreNote(p,F(1)) for p in g)) for i,g in enumerate(groups))
    return Exercise('Chords',tuple(p for e in events for p in e.pitches),events)


def event(pitch, time=0, kind='note_on', channel=0):
    return NoteEvent(pitch,0 if kind=='note_off' else 80,time,'test',kind,channel)


class ChordTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'chords.musicxml'

    def load(self, content, **kwargs):
        self.path.write_text(content,encoding='utf-8')
        return load_exercise(self.path,**kwargs)

    def test_chord_timing_and_rest(self):
        score=self.load(xml('<attributes><divisions>3</divisions></attributes>'+n(('C',4),3)+n(('E',4),2,'<chord/>')+n(('G',4),1,'<chord/>')+'<note><rest/><duration>3</duration><voice>1</voice></note>'+n(('D',4),1)))
        self.assertEqual(score.events[0].pitches,(60,64,67))
        self.assertEqual(tuple(t.duration for t in score.events[0].tones),(F(1),F(2,3),F(1,3)))
        self.assertEqual(score.events[1].onset,F(2))
        self.assertEqual((score.rests[0].onset,score.rests[0].duration),(F(1),F(1)))
        self.assertEqual(score.duration,F(7,3))

    def test_both_staves_merge_and_measure_extent_uses_longest_voice(self):
        first=n(('C',4),1)+n(('D',4),1)+'<backup><duration>2</duration></backup>'+n(('C',3),4,voice='5',staff='2')
        score=self.load(xml(first,n(('E',4))))
        self.assertEqual([e.pitches for e in score.events],[(48,60),(62,),(64,)])
        self.assertEqual(score.events[2].onset,F(4))
        filtered=self.load(xml(first,n(('E',4))),staff='1')
        self.assertEqual([e.pitches for e in filtered.events],[(60,),(62,),(64,)])
        self.assertEqual(filtered.events[2].onset,F(4))

    def test_partial_chord_tie_extends_only_tied_pitch(self):
        score=self.load(xml(n(('C',4),extra='<tie type="start"/>')+n(('E',4),extra='<chord/>'),
                            n(('C',4),extra='<tie type="stop"/>')+n(('G',4),extra='<chord/>')))
        self.assertEqual([e.pitches for e in score.events],[(60,64),(67,)])
        self.assertEqual(score.events[0].tones[0].duration,F(2))

    def test_invalid_chord_and_tie_gap(self):
        for content in [xml(n(('C',4),extra='<chord/>')),
                        xml(n(('C',4))+n(('E',4),2,'<chord/>')),
                        xml(n(('C',4),extra='<tie type="start"/>')+'<forward><duration>1</duration></forward>'+n(('C',4),extra='<tie type="stop"/>'))]:
            with self.subTest(content=content),self.assertRaises(ValueError):
                self.load(content)

    def test_json_chords_and_cli_demo(self):
        path=Path(self.temp.name)/'chords.json'
        path.write_text(json.dumps({'title':'Chords','notes':[[60,64,67],[62,65,69]]}))
        self.assertEqual(load_exercise(path).events[0].pitches,(60,64,67))
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['demo','--exercise',str(path),'--chords','60+64+67','62+65+69']),0)
        self.assertIn('Exercise complete',out.getvalue())
        self.assertNotIn('None',out.getvalue())

    def test_chord_requires_all_keys_still_held(self):
        tutor=Tutor(exercise((60,64,67)))
        self.assertIsNone(tutor.observe(event(60)))
        self.assertIsNone(tutor.observe(event(60,.01,'note_off')))
        tutor.observe(event(64,.02)); tutor.observe(event(67,.03))
        self.assertFalse(tutor.complete)
        self.assertIn('Correct',tutor.observe(event(60,.04)))

    def test_timing_window_and_retry(self):
        tutor=Tutor(exercise((60,64)))
        tutor.observe(event(60,0))
        self.assertIn('closer together',tutor.observe(event(64,.3)))
        self.assertFalse(tutor.complete)
        for p in (60,64): tutor.observe(event(p,.4,'note_off'))
        tutor.observe(event(64,.5))
        self.assertIn('Correct',tutor.observe(event(60,.6)))

    def test_extra_note_blocks_chord(self):
        tutor=Tutor(exercise((60,64)))
        tutor.observe(event(61))
        self.assertIn('Release',tutor.observe(event(60,.01)))
        tutor.observe(event(64,.02))
        self.assertFalse(tutor.complete)
        for p in (60,61,64): tutor.observe(event(p,.1,'note_off'))
        tutor.observe(event(60,.2))
        self.assertIn('Correct',tutor.observe(event(64,.21)))

    def test_releasing_extra_key_completes_pending_chord(self):
        tutor=Tutor(exercise((60,64)))
        tutor.observe(event(61))
        tutor.observe(event(60,.01)); tutor.observe(event(64,.02))
        self.assertIn('Correct',tutor.observe(event(61,.03,'note_off')))

    def test_releases_between_groups_are_silent(self):
        tutor=Tutor(exercise((60,64),(62,65)))
        tutor.observe(event(60)); tutor.observe(event(64,.01))
        self.assertIsNone(tutor.observe(event(60,.2,'note_off')))
        self.assertIsNone(tutor.observe(event(64,.2,'note_off')))

    def test_repeated_chord_needs_releases_and_new_attacks(self):
        tutor=Tutor(exercise((60,64),(60,64)))
        tutor.observe(event(60)); tutor.observe(event(64,.01))
        self.assertEqual(tutor.position,1)
        self.assertIn('Release and replay',tutor.observe(event(60,.02)))
        self.assertFalse(tutor.complete)
        for p in (60,64): tutor.observe(event(p,.1,'note_off'))
        tutor.observe(event(60,.2)); tutor.observe(event(64,.21))
        self.assertTrue(tutor.complete)

    def test_sustained_bass_is_allowed_at_next_attack(self):
        score=self.load(xml(n(('C',4))+n(('D',4))+'<backup><duration>2</duration></backup>'+n(('C',3),2,voice='5',staff='2')))
        tutor=Tutor(score)
        tutor.observe(event(48)); tutor.observe(event(60,.01))
        tutor.observe(event(60,.2,'note_off'))
        self.assertIn('Correct',tutor.observe(event(62,.3)))
        self.assertTrue(tutor.complete)

    def test_release_is_channel_specific(self):
        tutor=Tutor(exercise((60,64)))
        tutor.observe(event(60,channel=1))
        tutor.observe(event(60,.01,'note_off',channel=0))
        self.assertIn('Correct',tutor.observe(event(64,.02)))
        message=SimpleNamespace(type='note_on',note=60,velocity=0,channel=3)
        converted=event_from_message(message)
        self.assertEqual((converted.kind,converted.channel),('note_off',3))

    def test_callback_input_captures_releases_and_closes(self):
        class Port:
            closed=False
            def __enter__(self): return self
            def __exit__(self,*args): self.closed=True
        port=Port()
        def open_input(name,callback):
            for kind in ('note_on','note_off'):
                callback(SimpleNamespace(type=kind,note=60,velocity=80,channel=0))
            return port
        with patch('ada_piano.sound_sensor._mido',return_value=SimpleNamespace(open_input=open_input)):
            stream=midi_notes('test')
            self.assertEqual(next(stream).kind,'note_on')
            self.assertEqual(next(stream).kind,'note_off')
            stream.close()
        self.assertTrue(port.closed)

    def test_simulation_and_invalid_window(self):
        tutor=Tutor(exercise((60,64,67),(62,65,69)))
        for e in simulated_chords([(60,64,67),(62,65,69)]): tutor.observe(e)
        self.assertTrue(tutor.complete)
        for value in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError): Tutor(exercise((60,64)),value)
