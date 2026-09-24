"""Silent video preview. Only the decoder thread owns its VideoCapture."""
from dataclasses import dataclass
import math
import threading
import time

import cv2


class PlaybackClock:
    def __init__(self, duration, now=time.monotonic):
        self.duration = duration
        self.now = now
        self.anchor_time = now()
        self.anchor_position = 0.0
        self.speed = 1.0
        self.playing = False

    def position(self):
        elapsed = (self.now()-self.anchor_time)*self.speed if self.playing else 0
        return min(self.duration, self.anchor_position+elapsed)

    def seek(self, seconds):
        if not math.isfinite(seconds):
            raise ValueError("Playback time must be finite.")
        self.anchor_position = min(self.duration, max(0, seconds))
        self.anchor_time = self.now()

    def play(self):
        position = self.position()
        self.seek(0 if position >= self.duration else position)
        self.playing = True

    def pause(self):
        self.seek(self.position())
        self.playing = False

    def set_speed(self, speed):
        if not math.isfinite(speed) or not .25 <= speed <= 2:
            raise ValueError("Playback speed must be between 0.25x and 2x.")
        self.seek(self.position())
        self.speed = speed


@dataclass
class PlaybackFrame:
    seconds: float
    image: object
    ended: bool = False
    error: str = ""


class VideoPlayer:
    def __init__(self, path, duration, start=0):
        self.path = str(path)
        self.clock = PlaybackClock(duration)
        self.clock.seek(start)
        self.condition = threading.Condition()
        self.closed = False
        self.revision = 0
        self.pending = True
        self.latest = None
        self.thread = threading.Thread(target=self._decode, daemon=True)
        self.thread.start()

    @property
    def playing(self):
        with self.condition:
            return self.clock.playing

    @property
    def seeking(self):
        with self.condition:
            return self.pending

    def _invalidate(self):
        self.revision += 1
        self.latest = None
        self.condition.notify_all()

    def play(self, seconds=None):
        with self.condition:
            if seconds is not None:
                self.clock.seek(seconds)
            self.clock.play()
            self._invalidate()

    def pause(self):
        with self.condition:
            self.clock.pause()
            self._invalidate()

    def seek(self, seconds):
        with self.condition:
            self.clock.seek(seconds)
            self.pending = True
            self._invalidate()

    def set_speed(self, speed):
        with self.condition:
            self.clock.set_speed(speed)
            self._invalidate()

    def take_frame(self):
        with self.condition:
            result, self.latest = self.latest, None
            return result

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()

    def _decode(self):
        cap = None
        try:
            cap = cv2.VideoCapture(self.path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if not cap.isOpened() or fps <= 0 or total <= 0:
                raise ValueError("Cannot play this video.")
            next_index, displayed = 0, -1
            while True:
                with self.condition:
                    if self.closed:
                        return
                    seconds = self.clock.position()
                    ended = self.clock.playing and seconds >= self.clock.duration
                    target = min(total-1, int(seconds*fps))
                    if not self.pending and (not self.clock.playing or (target == displayed and not ended)):
                        self.condition.wait(.01 if self.clock.playing else None)
                        continue
                    revision = self.revision
                    seeking = self.pending
                if seeking or target < next_index or target-next_index > fps*2:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
                    next_index = target
                while next_index < target:
                    with self.condition:
                        if self.closed or revision != self.revision:
                            break
                    if not cap.grab():
                        raise RuntimeError("Could not advance the video decoder.")
                    next_index += 1
                with self.condition:
                    if self.closed:
                        return
                    if revision != self.revision:
                        continue
                # Re-read the final frame if EOF is reached after it was displayed.
                if target < next_index:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
                ok, frame = cap.read()
                next_index = target+1
                if not ok:
                    raise RuntimeError("Could not decode this frame. Try seeking to an earlier time.")
                with self.condition:
                    if self.closed:
                        return
                    if revision != self.revision:
                        continue
                    displayed = target
                    self.pending = False
                    self.latest = PlaybackFrame(target/fps, frame, ended)
                    if ended:
                        self.clock.pause()
                        self.clock.seek(self.clock.duration)
        except Exception as exc:
            with self.condition:
                if not self.closed:
                    self.clock.pause()
                    self.pending = False
                    self.latest = PlaybackFrame(0, None, error=str(exc))
        finally:
            if cap is not None:
                cap.release()
