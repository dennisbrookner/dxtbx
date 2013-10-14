# -*- mode: python; coding: utf-8; indent-tabs-mode: nil; python-indent: 2 -*-
#
# $Id$

from __future__ import division
from __future__ import print_function

from dxtbx.format.FormatPY import FormatPY


class FormatPYmultitile(FormatPY):
    @staticmethod
    def understand(image_file):
        try:
            stream = FormatPYmultitile.open_file(image_file, "rb")
            import cPickle as pickle

            data = pickle.load(stream)
        except IOError as e:
            return False

        wanted_header_items = ["TILES", "METROLOGY"]

        for header_item in wanted_header_items:
            if not header_item in data:
                return False

        unwanted_header_items = ["SIZE1", "SIZE2"]

        for header_item in unwanted_header_items:
            if header_item in data:
                return False

        return True

    def __init__(self, image_file):
        """Initialise the image structure from the given file."""

        assert self.understand(image_file)

        FormatPY.__init__(self, image_file)

    def _start(self):

        from xfel.cftbx.detector.cspad_detector import CSPadDetector

        self.detectorbase = CSPadDetector(self._image_file)
        self.detectorbase.readHeader()

    def _goniometer(self):

        return self._goniometer_factory.single_axis()

    def _detector(self):
        """Return a model for a simple detector"""

        return self._detector_factory.simple(
            sensor="PAD",
            distance=self.detectorbase.distance,
            beam_centre=(
                self.detectorbase.beam_center[0],
                self.detectorbase.beam_center[1],
            ),
            fast_direction="+x",
            slow_direction="-y",
            pixel_size=(
                self.detectorbase._pixel_size[0] * 1e3,
                self.detectorbase._pixel_size[1] * 1e3,
            ),
            image_size=(self.detectorbase.size1, self.detectorbase.size2),
            trusted_range=(0, self.detectorbase._saturation),
            mask=[],
        )  # a list of dead rectangles

    def _beam(self):
        """Return a simple model for the beam."""

        return self._beam_factory.simple(self.detectorbase._metrology_params.wavelength)

    def _scan(self):
        """Return the scan information for this image."""

        from calendar import timegm
        from time import strptime

        # Convert textual ISO 8601 timestamp in UTC to
        # millisecond-precision Unix epoch.
        str_min = self.detectorbase._metrology_params.timestamp[:16] + "UTC"
        str_sec = self.detectorbase._metrology_params.timestamp[17:]
        epoch = timegm(strptime(str_min, "%Y-%m-%dT%H:%M%Z")) + float(str_sec)

        return self._scan_factory.make_scan(
            image_range=(1, 1),
            exposure_time=1e-15 * self.detectorbase._metrology_params.pulse_length,
            oscillation=(0, 0),
            epochs={1: epoch},
        )


if __name__ == "__main__":

    import sys

    for arg in sys.argv[1:]:
        print(FormatPYmultitile.understand(arg))
