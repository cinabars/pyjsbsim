import time
from math import pi, sin
import pickle
import numpy as np
from utils import BinarySolver

class TrimPropertyProblem(object):

    def __init__(self, name, fdm):
        self.name = name
        self.fdm = fdm
        self.results = {}

    def setup(self, param):
        self.fdm.set_property_value(self.name, param)
        #print self.name, self.fdm.get_property_value(self.name)

    def save_current_as_guess(self):
        self.fdm.set_property_value("trim/solver/aileronGuess",
            self.fdm.get_property_value("fcs/aileron-cmd-norm"))
        self.fdm.set_property_value("trim/solver/elevatorGuess",
            self.fdm.get_property_value("fcs/elevator-cmd-norm"))
        self.fdm.set_property_value("trim/solver/rudderGuess",
            self.fdm.get_property_value("fcs/rudder-cmd-norm"))
        self.fdm.set_property_value("trim/solver/throttleGuess",
            self.fdm.get_property_value("fcs/throttle-cmd-norm"))
        self.fdm.set_property_value("trim/solver/alphaGuess",
            self.fdm.get_property_value("aero/alpha-rad"))
        self.fdm.set_property_value("trim/solver/betaGuess",
            self.fdm.get_property_value("aero/beta-rad"))

    def solve(self):
        try:
            self.fdm.do_trim(0)
            #self.fdm.do_simplex_trim(0)
            self.save_current_as_guess()
            catalog = self.fdm.get_property_catalog("/")

            # XXX why do we need to flip the sign of gamma here?
            self.fdm.set_property_value("ic/gamma-deg", self.fdm.get_property_value("ic/gamma-deg"))

            # compute fuel flow rates by running engines at trim for awhile
            num_engines = self.fdm.propulsion_get_num_engines()
            for i in range(num_engines):
                self.fdm.propulsion_init_running(i)
            for i in range(10):
                self.fdm.run()
                catalog_fuel = self.fdm.get_property_catalog("/")

            # copy fuel flow rates from catalog where engines were run
            for i in range(num_engines):
                if i == 0:
                    entry = ""
                else:
                    entry = "[{}]".format(i)
                catalog["propulsion/engine{}/fuel-flow-rate-pps".format(entry)]=\
                    catalog_fuel["propulsion/engine{}/fuel-flow-rate-pps".format(entry)]
            return True
        except:
            return False

class BadaData(object):

    def __init__(self, flight_levels, file_name):
        self.flight_levels = flight_levels
        self.file_name = file_name
        self.cruise = {}
        self.climb = {}
        self.descent = {}
        self.num_engines = 1

    def save(self):
        pickle.dump(self, open(self.file_name,"wb"))

    def __repr__(self):

        # load bada ptf template
        ptf_template = open("bada_ptf.template","rb").read()

        # roaw format string
        ptf_row_format = "{flight_level:3} |"\
            "{cruise_tas:5d} {cruise_fuelrate_low:6.1f} {cruise_fuelrate_nom:6.1f} {cruise_fuelrate_high:6.1f} |"\
            "{climb_tas:5d} {climb_roc_low:5d} {climb_roc_nom:4d} {climb_roc_high:4d} {climb_fuelrate_nom:8.1f}  |"\
            "{descent_tas:5d} {descent_rod:6d} {descent_fuelrate:7.1f}\n"\
            "    |                           |                                |                     \n"

        modes = ["low", "nom", "high"]
        table = ""

        # conversions
        pps2kgpm = 27.2155422
        fps2fpm = 60
        lbs2kg = 0.453592

        valid_flight_levels = []
        for fl in self.cruise.keys():
            valid_flight_levels.append(int(fl))
        valid_flight_levels.sort()

        if valid_flight_levels == []:
            return "No valid flight levels"

        # write table entries
        for fl in valid_flight_levels:
            fl_str = str(fl)

            # compute total fuel flow rates
            cruise_fuelrate_low = 0
            cruise_fuelrate_nom = 0
            cruise_fuelrate_high = 0
            climb_fuelrate_nom = 0
            descent_fuelrate = 0
            for i in range(self.num_engines):
                if i == 0:
                    entry = ""
                else:
                    entry = "[{}]".format(i)
                cruise_fuelrate_low += pps2kgpm*\
                    self.cruise[fl_str]["low"]["propulsion/engine{}/fuel-flow-rate-pps".format(entry)]
                cruise_fuelrate_nom += pps2kgpm*\
                    self.cruise[fl_str]["nom"]["propulsion/engine{}/fuel-flow-rate-pps".format(entry)]
                cruise_fuelrate_high += pps2kgpm*\
                    self.cruise[fl_str]["high"]["propulsion/engine{}/fuel-flow-rate-pps".format(entry)]
                climb_fuelrate_nom += pps2kgpm*\
                    self.climb[fl_str]["nom"]["propulsion/engine{}/fuel-flow-rate-pps".format(entry)]
                descent_fuelrate += pps2kgpm*\
                    self.descent[fl_str]["propulsion/engine{}/fuel-flow-rate-pps".format(entry)]

            # write a row in the table
            table += ptf_row_format.format(
                    flight_level=int(fl),

                    # cruise
                    cruise_tas=int(self.cruise[fl_str]["nom"]["ic/vt-kts"]),
                    cruise_fuelrate_low=cruise_fuelrate_low,
                    cruise_fuelrate_nom=cruise_fuelrate_nom,
                    cruise_fuelrate_high=cruise_fuelrate_high,

                    # climb
                    climb_tas=int(self.climb[fl_str]["nom"]["ic/vt-kts"]),
                    climb_roc_low= int(
                        sin(pi/180*self.climb[fl_str]["low"]["ic/gamma-deg"])*
                        self.climb[fl_str]["low"]["ic/vt-fps"]*fps2fpm),
                    climb_roc_nom= int(
                        sin(pi/180*self.climb[fl_str]["nom"]["ic/gamma-deg"])*
                        self.climb[fl_str]["nom"]["ic/vt-fps"]*fps2fpm),
                    climb_roc_high= int(
                        sin(pi/180*self.climb[fl_str]["high"]["ic/gamma-deg"])*
                        self.climb[fl_str]["high"]["ic/vt-fps"]*fps2fpm),
                    climb_fuelrate_nom=climb_fuelrate_nom,

                    # descent
                    descent_tas=int(self.descent[fl_str]["ic/vt-kts"]),
                    descent_rod=-int(
                        sin(pi/180*self.descent[fl_str]["ic/gamma-deg"])*
                        self.descent[fl_str]["ic/vt-fps"]*fps2fpm),
                    descent_fuelrate=descent_fuelrate,
                )

        # find max altitude
        fl_key = self.cruise.keys()[0]
        max_alt=max(100*np.array(valid_flight_levels))

        return ptf_template.format(
            table=table,

            # header
            date=time.strftime("%b %d %Y"),
            name=self.file_name,

            # climb
            climb_cas_low=int(self.climb[fl_key]["low"]["ic/vc-kts"]),
            climb_cas_high=int(self.climb[fl_key]["high"]["ic/vc-kts"]),
            climb_mach=self.climb[fl_key]["nom"]["ic/mach"],

            # cruise
            cruise_cas_low=int(self.cruise[fl_key]["low"]["ic/vc-kts"]),
            cruise_cas_high=int(self.cruise[fl_key]["high"]["ic/vc-kts"]),
            cruise_mach=self.cruise[fl_key]["nom"]["ic/mach"],

            # descent
            descent_cas_low=int(self.descent[fl_key]["ic/vc-kts"]),
            descent_cas_high=int(self.descent[fl_key]["ic/vc-kts"]),
            descent_mach=self.descent[fl_key]["ic/mach"],

            # mass
            low_mass=int(self.cruise[fl_key]["low"]["inertia/weight-lbs"]*lbs2kg),
            nom_mass=int(self.cruise[fl_key]["nom"]["inertia/weight-lbs"]*lbs2kg),
            high_mass=int(self.cruise[fl_key]["high"]["inertia/weight-lbs"]*lbs2kg),

            # max alt
            max_alt=int(max_alt),
        )

    @classmethod
    def from_fdm(cls, fdm, flight_levels, file_name, verbose=False):

        data = cls(flight_levels, file_name);
        solver = BinarySolver(verbose=verbose)
        data.num_engines = fdm.propulsion_get_num_engines()

        for fl in flight_levels:

            try:

                # flight level as string
                fl_str = str(fl)

                # calculate altitude from flight level
                alt = 100*fl
                # can't fly on ground
                if alt <= 10: alt = 10
                fdm.set_property_value("ic/h-agl-ft", alt)

                print "=================================="
                print "flight level: {}\n".format(fl)
                print "=================================="

                gammaProb = TrimPropertyProblem("ic/gamma-deg",fdm)

                # cruise
                cruise_catalog = {}
                fdm.set_property_value("ic/gamma-deg", 0)
                for mode in ["low", "nom", "high"]:
                    start = time.time()
                    fdm.setup_bada_trim(mode)
                    gammaProb.setup(0)
                    gammaProb.solve()
                    cruise_catalog[mode] = fdm.get_property_catalog("/")
                    print "\ncruise {} trim finished:\n" \
                        "elapsed time\t: {} sec\n".format(mode,
                        time.time()-start)

                # max climb rate
                climb_catalog = {}
                for mode in ["low", "nom", "high"]:
                    start = time.time()
                    fdm.setup_bada_trim(mode)
                    solver.solve(gammaProb,
                        prob_type="max", x_guess=0, x_min=0, x_max=50, tol=0.1)
                    climb_catalog[mode] = fdm.get_property_catalog("/")
                    print "\nmax climb {} trim finished:\n" \
                        "elapsed time\t: {} sec\ngamma\t: {}\n".format(
                            mode,
                            time.time()-start,
                            fdm.get_property_value("ic/gamma-deg"))

                # max descent rate
                start = time.time()
                fdm.setup_bada_trim("nom")
                solver.solve(gammaProb,
                    prob_type="min", x_guess=0, x_min=-50, x_max=0, tol=0.1)
                descent_catalog = fdm.get_property_catalog("/")
                print "\nmax descent trim finished:\n" \
                    "elapsed time\t: {} sec\ngamma\t: {}\n".format(
                    time.time()-start, fdm.get_property_value("ic/gamma-deg"))

                # save data after each step
                data.cruise[fl_str] = cruise_catalog
                data.climb[fl_str] = climb_catalog
                data.descent[fl_str] = descent_catalog
                data.save()

            except RuntimeError as e:
                print e
                continue

        data.save()
        return data
