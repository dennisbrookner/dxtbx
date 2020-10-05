from __future__ import absolute_import, division, print_function

import os
import sys
from builtins import range

import numpy as np
import psana

from libtbx.phil import parse
from scitbx.array_family import flex
from scitbx.matrix import col

from cctbx.eltbx import attenuation_coefficient

from dxtbx.format.FormatXTC import FormatXTC, locator_str
from dxtbx.model import Detector, ParallaxCorrectedPxMmStrategy

try:
    from xfel.cxi.cspad_ana import cspad_tbx
except ImportError:
    # xfel not configured
    pass

jungfrau_locator_str = """
  jungfrau {
    dark = True
      .type = bool
      .help = Dictates if dark subtraction is done from raw data
    monolithic = False
      .type = bool
      .help = switch to FormatXTCJungfrauMonolithic if True. Used for LS49 image averaging
    use_big_pixels = True
      .type = bool
      .help = account for multi-sized pixels in the 512x1024 Jungfrau panels, forming a 514x1030 pixel panel
  }
"""

jungfrau_locator_scope = parse(
    jungfrau_locator_str + locator_str, process_includes=True
)


class FormatXTCJungfrau(FormatXTC):
    def __init__(self, image_file, **kwargs):
        super(FormatXTCJungfrau, self).__init__(
            image_file, locator_scope=jungfrau_locator_scope, **kwargs
        )
        self._ds = FormatXTC._get_datasource(image_file, self.params)
        self._env = self._ds.env()
        self.populate_events()
        self.n_images = len(self.times)
        self._cached_detector = {}
        self._cached_psana_detectors = {}
        self._beam_index = None
        self._beam_cache = None

        self._dist_det = None

    @staticmethod
    def understand(image_file):
        try:
            params = FormatXTC.params_from_phil(jungfrau_locator_scope, image_file)
        except Exception:
            return False
        return any(["jungfrau" in src.lower() for src in params.detector_address])

    def get_raw_data(self, index):
        from xfel.util import jungfrau

        d = FormatXTCJungfrau.get_detector(self, index)
        evt = self._get_event(index)
        run = self.get_run_from_index(index)
        if run.run() not in self._cached_psana_detectors:
            assert len(self.params.detector_address) == 1
            self._cached_psana_detectors[run.run()] = psana.Detector(
                self.params.detector_address[0], self._env
            )
        det = self._cached_psana_detectors[run.run()]
        data = det.calib(evt)
        data = data.astype(np.float64)
        self._raw_data = []
        for module_count, module in enumerate(d.hierarchy()):

            if (
                self.params.jungfrau.use_big_pixels
                and os.environ.get("DONT_USE_BIG_PIXELS_JUNGFRAU") is None
            ):
                panel_data = jungfrau.correct_panel(data[module_count])
                self._raw_data.append(flex.double(panel_data))
                continue

            for asic_count, asic in enumerate(module):
                fdim, sdim = asic.get_image_size()
                sensor_id = asic_count // 4  # There are 2X4 asics per module
                asic_in_sensor_id = asic_count % 4  # this number will be 0,1,2 or 3
                asic_data = data[module_count][
                    sensor_id * sdim : (sensor_id + 1) * sdim,
                    asic_in_sensor_id * fdim : (asic_in_sensor_id + 1) * fdim,
                ]  # 8 sensors per module
                self._raw_data.append(flex.double(np.array(asic_data)))
        assert len(d) == len(self._raw_data), (len(d), len(self._raw_data))
        return tuple(self._raw_data)

    def get_num_images(self):
        return self.n_images

    def get_detector(self, index=None):
        return FormatXTCJungfrau._detector(self, index)

    def get_beam(self, index=None):
        if self._beam_index != index:
            self._beam_index = index
            self._beam_cache = self._beam(index)
        return self._beam_cache

    def _beam(self, index=None):
        """Returns a simple model for the beam"""
        if index is None:
            index = 0
        evt = self._get_event(index)
        wavelength = cspad_tbx.evt_wavelength(evt)
        if wavelength is None:
            return None
        #shift = -0.0221 #aaron's math, day2
        shift = -0.02386 #good math day3
        if self.params.experiment is not None and 'lv95' in self.params.experiment:
            wavelength += shift
        elif self.params.data_source is not None and 'lv95' in self.params.data_source:
            wavelength += shift
        
        return self._beam_factory.simple(wavelength)

    def get_goniometer(self, index=None):
        return None

    def get_scan(self, index=None):
        return None

    def _detector(self, index=None):
        from xfel.cftbx.detector.cspad_cbf_tbx import basis_from_geo
        from PSCalib.SegGeometryStore import sgs

        run = self.get_run_from_index(index)
        if run.run() in self._cached_detector:
            return self._cached_detector[run.run()]

        if index is None:
            index = 0
        self._env = self._ds.env()
        assert len(self.params.detector_address) == 1
        self._det = psana.Detector(self.params.detector_address[0], self._env)
        evt = self._get_event(index)

        if self._dist_det is None:
            self._dist_det = psana.Detector('CXI:DS1:MMS:06.RBV')
        distance = self._dist_det(evt) + 573.3387

        geom = self._det.pyda.geoaccess(evt.run())
        pixel_size = (
            self._det.pixel_size(self._get_event(index)) / 1000.0
        )  # convert to mm
        d = Detector()
        pg0 = d.hierarchy()
        # first deal with D0
        det_num = 0
        root = geom.get_top_geo()
        root_basis = basis_from_geo(root)
        while len(root.get_list_of_children()) == 1:
            sub = root.get_list_of_children()[0]
            sub_basis = basis_from_geo(sub)
            root = sub
            root_basis = root_basis * sub_basis
        t = root_basis.translation
        root_basis.translation = col((t[0], t[1], -distance))

        origin = col((root_basis * col((0, 0, 0, 1)))[0:3])
        fast = col((root_basis * col((1, 0, 0, 1)))[0:3]) - origin
        slow = col((root_basis * col((0, 1, 0, 1)))[0:3]) - origin
        pg0.set_local_frame(fast.elems, slow.elems, origin.elems)
        pg0.set_name("D%d" % (det_num))

        # Now deal with modules
        for module_num in range(len(root.get_list_of_children())):
            module = root.get_list_of_children()[module_num]
            module_basis = basis_from_geo(module)
            origin = col((module_basis * col((0, 0, 0, 1)))[0:3])
            fast = col((module_basis * col((1, 0, 0, 1)))[0:3]) - origin
            slow = col((module_basis * col((0, 1, 0, 1)))[0:3]) - origin
            pg1 = pg0.add_group()
            pg1.set_local_frame(fast.elems, slow.elems, origin.elems)
            pg1.set_name("D%dM%d" % (det_num, module_num))

            # Read the known layout of the Jungfrau 2x4 module
            sg = sgs.Create(segname=module.oname)
            xx, yy = sg.get_seg_xy_maps_um()
            xx = xx / 1000
            yy = yy / 1000

            # Now deal with ASICs
            for asic_num in range(8):
                val = "ARRAY_D0M%dA%d" % (module_num, asic_num)
                dim_slow = xx.shape[0]
                dim_fast = xx.shape[1]
                sensor_id = asic_num // 4  # There are 2X4 asics per module
                asic_in_sensor_id = asic_num % 4  # this number will be 0,1,2 or 3
                id_slow = sensor_id * (dim_slow // 2)
                id_fast = asic_in_sensor_id * (dim_fast // 4)
                origin = col((xx[id_slow][id_fast], yy[id_slow][id_fast], 0))
                fp = col((xx[id_slow][id_fast + 1], yy[id_slow][id_fast + 1], 0))
                sp = col((xx[id_slow + 1][id_fast], yy[id_slow + 1][id_fast], 0))
                fast = (fp - origin).normalize()
                slow = (sp - origin).normalize()
                p = pg1.add_panel()
                p.set_local_frame(fast.elems, slow.elems, origin.elems)
                p.set_pixel_size((pixel_size, pixel_size))
                p.set_trusted_range((-10, 2e6))
                p.set_name(val)

                thickness, material = 0.32, "Si"
                p.set_thickness(thickness)  # mm
                p.set_material(material)
                # Compute the attenuation coefficient.
                # This will fail for undefined composite materials
                # mu_at_angstrom returns cm^-1, but need mu in mm^-1
                table = attenuation_coefficient.get_table(material)
                wavelength = self.get_beam(index).get_wavelength()
                mu = table.mu_at_angstrom(wavelength) / 10.0
                p.set_mu(mu)
                p.set_px_mm_strategy(ParallaxCorrectedPxMmStrategy(mu, thickness))

                if (
                    self.params.jungfrau.use_big_pixels
                    and os.environ.get("DONT_USE_BIG_PIXELS_JUNGFRAU") is None
                ):
                    p.set_image_size((1030, 514))
                    break
                else:
                    p.set_image_size((dim_fast // 4, dim_slow // 2))
        if (
            self.params.jungfrau.use_big_pixels
            and os.environ.get("DONT_USE_BIG_PIXELS_JUNGFRAU") is None
        ):
            assert len(d) == 8
        self._cached_detector[run.run()] = d
        return d


class FormatXTCJungfrauMonolithic(FormatXTCJungfrau):
    """Monolithic version of the Jungfrau, I.E. use the psana detector image function to assemble a monolithic image"""

    @staticmethod
    def understand(image_file):
        try:
            params = FormatXTC.params_from_phil(jungfrau_locator_scope, image_file)
            if params.jungfrau.monolithic:
                return True
            return False
        except Exception:
            return False

    def get_raw_data(self, index):
        self.get_detector(index)  # is this line required?
        evt = self._get_event(index)
        run = self.get_run_from_index(index)
        if run.run() not in self._cached_psana_detectors:
            assert len(self.params.detector_address) == 1
            self._cached_psana_detectors[run.run()] = psana.Detector(
                self.params.detector_address[0], self._env
            )
        det = self._cached_psana_detectors[run.run()]
        data = det.image(evt)
        data = data.astype(np.float64)
        self._raw_data = flex.double(data)
        return self._raw_data

    def get_detector(self, index=None):
        return self._detector(index)

    def _detector(self, index=None):
        return self._detector_factory.simple(
            sensor="UNKNOWN",
            distance=100.0,
            beam_centre=(50.0, 50.0),
            fast_direction="+x",
            slow_direction="-y",
            pixel_size=(0.075, 0.075),
            image_size=(1030, 1064),
            trusted_range=(-10, 2e6),
            mask=[],
        )


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        # Bug, should call this part differently for understand method to work
        print(FormatXTCJungfrau.understand(arg))
