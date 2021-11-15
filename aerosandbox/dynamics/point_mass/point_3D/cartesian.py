from aerosandbox.dynamics.point_mass.common_point_mass import _DynamicsPointMassBaseClass
from aerosandbox.weights.mass_properties import MassProperties
import aerosandbox.numpy as np
from typing import Union, Dict, Tuple


class DynamicsPointMass3DCartesian(_DynamicsPointMassBaseClass):
    """
    Dynamics instance:
    * simulating a point mass
    * in 3D
    * with velocity parameterized in cartesian coordinates
    * assuming coordinated flight (i.e., sideslip = 0, bank angle = 0)

    State variables:
        x_e: x-position, in Earth axes. [meters]
        y_e: y-position, in Earth axes. [meters]
        z_e: z-position, in Earth axes. [meters]
        u_e: x-velocity, in Earth axes. [m/s]
        v_e: v-velocity, in Earth axes. [m/s]
        w_e: z-velocity, in Earth axes. [m/s]

    Control variables:
        Fx_e: Force along the Earth-x axis. [N]
        Fy_e: Force along the Earth-y axis. [N]
        Fz_e: Force along the Earth-z axis. [N]
        bank: Bank angle; used when applying wind-axes forces. [rad]

    """

    def __init__(self,
                 mass_props: MassProperties = None,
                 x_e: Union[np.ndarray, float] = 0,
                 y_e: Union[np.ndarray, float] = 0,
                 z_e: Union[np.ndarray, float] = 0,
                 u_e: Union[np.ndarray, float] = 0,
                 v_e: Union[np.ndarray, float] = 0,
                 w_e: Union[np.ndarray, float] = 0,
                 bank: Union[np.ndarray, float] = 0,
                 ):
        # Initialize state variables
        self.mass_props = MassProperties() if mass_props is None else mass_props
        self.x_e = x_e
        self.y_e = y_e
        self.z_e = z_e
        self.u_e = u_e
        self.v_e = v_e
        self.w_e = w_e

        # Initialize control variables
        self.Fx_e = 0
        self.Fy_e = 0
        self.Fz_e = 0
        self.bank = bank

    @property
    def state(self) -> Dict[str, Union[float, np.ndarray]]:
        return {
            "x_e": self.x_e,
            "y_e": self.y_e,
            "z_e": self.z_e,
            "u_e": self.u_e,
            "v_e": self.v_e,
            "w_e": self.w_e,
        }

    @property
    def control_variables(self) -> Dict[str, Union[float, np.ndarray]]:
        return {
            "Fx_e": self.Fx_e,
            "Fy_e": self.Fy_e,
            "Fz_e": self.Fz_e,
            "bank": self.bank,
        }

    def state_derivatives(self) -> Dict[str, Union[float, np.ndarray]]:
        return {
            "x_e": self.u_e,
            "y_e": self.v_e,
            "z_e": self.w_e,
            "u_e": self.Fx_e / self.mass_props.mass,
            "v_e": self.Fy_e / self.mass_props.mass,
            "w_e": self.Fz_e / self.mass_props.mass,
        }

    @property
    def speed(self) -> float:
        return (
                       self.u_e ** 2 +
                       self.v_e ** 2 +
                       self.w_e ** 2
               ) ** 0.5

    @property
    def gamma(self):
        """
        Returns the flight path angle, in radians.

        Positive flight path angle indicates positive vertical speed.

        """
        return np.arctan2(
            -self.w_e,
            (
                    self.u_e ** 2 +
                    self.v_e ** 2
            ) ** 0.5
        )

    @property
    def heading(self):
        """
        Returns the heading angle, in radians.

        * Heading 0 == North == aligned with x_e axis
        * Heading np.pi / 2 == East == aligned with y_e axis

        """
        return np.arctan2(
            self.v_e,
            self.u_e,
        )

    def convert_axes(self,
                     x_from: float,
                     y_from: float,
                     z_from: float,
                     from_axes: str,
                     to_axes: str,
                     ) -> Tuple[float, float, float]:
        if from_axes == "wind" or to_axes == "wind":
            rot_w_to_e = np.rotation_matrix_from_euler_angles(
                roll_angle=self.bank,
                pitch_angle=self.gamma,
                yaw_angle=self.heading,
                as_array=False
            )

        if from_axes == "earth":
            x_e = x_from
            y_e = y_from
            z_e = z_from
        elif from_axes == "wind":
            x_e = rot_w_to_e[0][0] * x_from + rot_w_to_e[0][1] * y_from + rot_w_to_e[0][2] * z_from
            y_e = rot_w_to_e[1][0] * x_from + rot_w_to_e[1][1] * y_from + rot_w_to_e[1][2] * z_from
            z_e = rot_w_to_e[2][0] * x_from + rot_w_to_e[2][1] * y_from + rot_w_to_e[2][2] * z_from
        else:
            raise ValueError("Bad value of `from_axes`!")

        if to_axes == "earth":
            x_to = x_e
            y_to = y_e
            z_to = z_e
        elif to_axes == "wind":
            x_to = rot_w_to_e[0][0] * x_e + rot_w_to_e[1][0] * y_e + rot_w_to_e[2][0] * z_e
            y_to = rot_w_to_e[0][1] * x_e + rot_w_to_e[1][1] * y_e + rot_w_to_e[2][1] * z_e
            z_to = rot_w_to_e[0][2] * x_e + rot_w_to_e[1][2] * y_e + rot_w_to_e[2][2] * z_e
        else:
            raise ValueError("Bad value of `to_axes`!")

        return x_to, y_to, z_to

    def add_force(self,
                  Fx: Union[np.ndarray, float] = 0,
                  Fy: Union[np.ndarray, float] = 0,
                  Fz: Union[np.ndarray, float] = 0,
                  axes="earth",
                  ) -> None:
        Fx_e, Fy_e, Fz_e = self.convert_axes(
            x_from=Fx,
            y_from=Fy,
            z_from=Fz,
            from_axes=axes,
            to_axes="earth"
        )
        self.Fx_e = self.Fx_e + Fx_e
        self.Fy_e = self.Fy_e + Fy_e
        self.Fz_e = self.Fz_e + Fz_e


if __name__ == '__main__':
    dyn = DynamicsPointMass3DCartesian()