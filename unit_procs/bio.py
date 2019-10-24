# This file is part of PooPyLab.
#
# PooPyLab is a simulation software for biological wastewater treatment
# processes using International Water Association Activated Sludge Models.
#    
#    Copyright (C) Kai Zhang
#
#    PooPyLab is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    PooPyLab is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with PooPyLab.  If not, see <http://www.gnu.org/licenses/>.
#
# This is the definition of class related to biological processes. 
# 
# ----------------------------------------------------------------------------


from unit_procs.streams import pipe
from ASMModel.asm_1 import ASM_1
from ASMModel import constants


# ----------------------------------------------------------------------------

class asm_reactor(pipe):
    __id = 0

    def __init__(self, ActiveVol=38000, swd=3.5,
                    Temperature=20, DO=2, *args, **kw):
        # swd = side water depth in meters, default = ~12 ft
        # ActiveVol in m^3, default value equals to 100,000 gallons
        # Temperature = 20 C by default
        # DO = dissolved oxygen, default = 2.0 mg/L

        pipe.__init__(self) 
        self.__class__.__id += 1
        self.__name__ = "ASMReactor_" + str(self.__id)

        self._type = "ASMReactor"

        self._active_vol = ActiveVol
        self._swd = swd
        self._area = self._active_vol / self._swd

        self._sludge = ASM_1(Temperature, DO)

        self._in_comps = [0.0] * constants._NUM_ASM1_COMPONENTS 
        self._mo_comps = [0.0] * constants._NUM_ASM1_COMPONENTS

        # results of previous round
        self._prev_mo_comps = [0.0] * constants._NUM_ASM1_COMPONENTS
        self._prev_so_comps = self._prev_mo_comps

        self._upstream_set_mo_flow = True
        
        self._int_step_sol = self._int_step_part = 1E-4

        return None


    # ADJUSTMENTS TO COMMON INTERFACE
    #
    def discharge(self):
        self._branch_flow_helper()
        self._prev_mo_comps = self._mo_comps[:]
        self._prev_so_comps = self._mo_comps[:]

        self.integrate(7, 'Euler', 0.05, 2.0)
        self._so_comps = self._mo_comps[:]
        self._discharge_main_outlet()

        return None

    # END OF ADJUSTMENTS TO COMMON INTERFACE

    
    # FUNCTIONS UNIQUE TO THE ASM_REACTOR CLASS
    #
    # (INSERT CODE HERE)
    #

    def assign_initial_guess(self, initial_guess):
        ''' 
        Assign the initial guess into _sludge.comps
        '''
        self._sludge._comps = initial_guess[:]
        self._mo_comps = initial_guess[:]  # CSTR: outlet = mixed liquor
        return None


    def set_active_vol(self, vol=380):
        # vol in M3
        if vol > 0:
            self._active_vol = vol
        else:
            print("ERROR:", self.__name__, "requires an active vol > 0 M3.")
        return None


    def get_active_vol(self):
        return self._active_vol


    def set_model_condition(self, Temperature, DO):
        if Temperature >= 4 and DO >= 0:
            self._sludge.update(Temperature, DO)
        else:
            print("ERROR:", self.__name__, "given crazy temperature or DO.")
        return None

   
    def get_model_params(self):
        return self._sludge.get_params()


    def get_model_stoichs(self):
        return self._sludge.get_stoichs()


    def integrate(self, 
            first_index_particulate=7,
            method_name='RK4',
            f_s=0.05,
            f_p=2.0):
        '''
        Integrate the model forward in time.
        '''
        # first_index_particulate: first index of particulate model component 
        # method_name = 'RK4' | 'Euler'
        # f_s: fraction of max step for soluble model components, typ=5%-20%
        # f_p: fraction of max step for particulate model components, typ=2.0

        if method_name == 'Euler':
            self._euler(first_index_particulate, f_s, f_p)
        else:
            self._runge_kutta_4(first_index_particulate, f_s, f_p)
        
        return None


    def _runge_kutta_4(self, first_index_part, f_s, f_p):
        '''
        Integration by using Runge-Kutta 4th order method.
        '''
        # first_index_part: first index of particulate model component,
        #   assuming all components before this index are soluble, and all
        #   starting this index are particulate in the matrix.
        # f_s: fraction of max step for soluble model components, typ=5%-20%
        # f_p: fraction of max step for particulate model components, typ=2.0

        # Determine the next step size based on:
        #   C(t + del_t) = C(t) + (dC/dt) * del_t, where
        #   0 < del_t < Retention_Time_C_k, where
        #   C is the individual model component and k is the kth reactor
        _del_C_del_t = self._sludge._dCdt(
                            self._active_vol,
                            self._total_inflow,
                            self._in_comps, 
                            self._mo_comps)

        #print('_del_C_del_t:{}'.format(_del_C_del_t))

        _uppers_sol = []
        _uppers_part = []

        for i in range(first_index_part):
            # screen out the zero items in _del_C_del_t
            if _del_C_del_t[i] != 0:
                #_uppers_sol.append(self._mo_comps[i] / abs(_del_C_del_t[i]))
                _uppers_sol.append(self._sludge._comps[i] 
                        / abs(_del_C_del_t[i]))

        for j in range(first_index_part, len(_del_C_del_t)):
            # screen out the zero items in _del_C_del_t
            if _del_C_del_t[j] != 0:
                #_uppers_part.append(self._mo_comps[j] / abs(_del_C_del_t[j]))
                _uppers_part.append(self._sludge._comps[j] 
                        / abs(_del_C_del_t[j]))

    
        _max_step_sol = min(_uppers_sol)
        _max_step_part = min(_uppers_part)

        _step_sol = f_s * _max_step_sol
        _step_part = f_p * _max_step_part

        #self._int_step_sol = min(self._int_step_sol, _new_step_sol)
        #print('step_sol = ', self._int_step_sol)

        #print('sol. step = {}, part. step = {}'.format(_step_sol, _step_part))

        # mid-point version of RK4, using half the given step size:
        #sz_2 = _step / 2
        sz_2 = _step_sol / 2  #TODO: use soluble step for all for now

        # _w1 = yn = self._mo_comps
        # k1 is idetical to _del_C_del_t calculated above
        k1 = _del_C_del_t 

        # _w2 = y_n + _step/2 * k1
        _w2 = [self._mo_comps[i] + sz_2 * k1[i] for i in range(len(k1))]

        k2 = self._sludge._dCdt(
                            self._active_vol,
                            self._total_inflow,
                            self._in_comps,
                            _w2)

        # _w3 = y_n + _step/2 * k2
        _w3 = [self._mo_comps[i] + sz_2 * k2[i] for i in range(len(k2))]

        k3 = self._sludge._dCdt(
                            self._active_vol,
                            self._total_inflow,
                            self._in_comps,
                            _w3)

        # _w4 = yn + _step * k3
        _w4 = [self._mo_comps[i] + _step_sol * k3[i] for i in range(len(k3))]

        k4 = self._sludge._dCdt(
                            self._active_vol,
                            self._total_inflow,
                            self._in_comps,
                            _w4)

        self._sludge._comps = [self._sludge._comps[i]
                                + (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]) / 6
                                * _step_sol
                                for i in range(len(self._sludge._comps))]

        self._mo_comps = self._so_comps = self._sludge._comps[:]

        return None


    def _euler(self, first_index_part=7, f_s=0.05, f_p=2.0):
        '''
        Integration by using Euler's method, aka RK1
        '''

        # first_index_part: first index of particulate model component,
        #   assuming all components before this index are soluble, and all
        #   starting this index are particulate in the matrix.
        # f_s: fraction of max step for soluble model components, typ=5%-20%
        # f_p: fraction of max step for particulate model components, typ=2.0

        # Determine the next step size based on:
        #   C(t + del_t) = C(t) + (dC/dt) * del_t, where
        #   0 < del_t < Retention_Time_C_k, where
        #   C is the individual model component and k is the kth reactor
        _del_C_del_t = self._sludge._dCdt(
                            self._active_vol,
                            self._total_inflow,
                            self._in_comps, 
                            self._mo_comps)

        #print('_del_C_del_t:{}'.format(_del_C_del_t))

        _uppers_sol = []
        _uppers_part = []

        for i in range(first_index_part):
            # screen out the zero items in _del_C_del_t
            if _del_C_del_t[i] != 0:
                #_uppers_sol.append(self._mo_comps[i] / abs(_del_C_del_t[i]))
                _uppers_sol.append(self._sludge._comps[i] 
                        / abs(_del_C_del_t[i]))

        for j in range(first_index_part, len(_del_C_del_t)):
            # screen out the zero items in _del_C_del_t
            if _del_C_del_t[j] != 0:
                #_uppers_part.append(self._mo_comps[j] / abs(_del_C_del_t[j]))
                _uppers_part.append(self._sludge._comps[j] 
                        / abs(_del_C_del_t[j]))

    
        _max_step_sol = min(_uppers_sol)
        _max_step_part = min(_uppers_part)

        _step_sol = f_s * _max_step_sol
        _step_part = f_s * _max_step_part

        #self._int_step_sol = min(self._int_step_sol, _new_step_sol)
        #print('step_sol = ', self._int_step_sol)

        #print('sol. step = {}, part. step = {}'.format(_step_sol, _step_part))

        # TODO: use the same time step before further optimization
        #for i in range(first_index_particulate):
            #self._mo_comps[i] += _del_C_del_t[i] * self._int_step_sol
            
        #for j in range(first_index_particulate, len(self._mo_comps)):
            #self._mo_comps[j] += _del_C_del_t[j] * self._int_step_part

        for i in range(len(self._mo_comps)):
            self._sludge._comps[i] += _del_C_del_t[i] * _step_sol

        self._so_comps = self._mo_comps = self._sludge._comps[:]

        return None

            
    #
    # END OF FUNCTIONS UNIQUE TO THE ASM_REACTOR CLASS

