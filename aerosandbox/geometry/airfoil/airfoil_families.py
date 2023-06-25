import aerosandbox.numpy as np
from scipy.special import comb
from aerosandbox.geometry.polygon import stack_coordinates
import re
from typing import Union
import os
from typing import List, Optional

_default_n_points_per_side = 200


def get_NACA_coordinates(
        name: str = None,
        n_points_per_side: int = _default_n_points_per_side,
        max_camber: float = None,
        camber_loc: float = None,
        thickness: float = None,
) -> np.ndarray:
    """
    Returns the coordinates of a 4-series NACA airfoil.

    Can EITHER specify `name`, or all three of `max_camber`, `camber_loc`, and `thickness` - not both.

    Args:

        Either:

            * name: Name of the NACA airfoil, as a string (e.g., "naca2412")

        Or:

            * All three of:

                max_camber: Maximum camber of the airfoil, as a fraction of chord (e.g., 0.02)

                camber_loc: The location of maximum camber, as a fraction of chord (e.g., 0.40)

                thickness: The maximum thickness of the airfoil, as a fraction of chord (e.g., 0.12)

        n_points_per_side: Number of points per side of the airfoil (top/bottom).

    Returns: The coordinates of the airfoil as a Nx2 ndarray [x, y]

    """
    ### Validate inputs
    name_specified = name is not None
    params_specified = [
        (max_camber is not None),
        (camber_loc is not None),
        (thickness is not None)
    ]

    if name_specified:
        if any(params_specified):
            raise ValueError(
                "Cannot specify both `name` and (`max_camber`, `camber_loc`, `thickness`) parameters - must be one or the other.")

        name = name.lower().strip()

        if not "naca" in name:
            raise ValueError("Not a NACA airfoil - name must start with 'naca'!")

        nacanumber = name.split("naca")[1]
        if not nacanumber.isdigit():
            raise ValueError("Couldn't parse the number of the NACA airfoil!")

        if not len(nacanumber) == 4:
            raise NotImplementedError("Only 4-digit NACA airfoils are currently supported!")

        # Parse
        max_camber = int(nacanumber[0]) * 0.01
        camber_loc = int(nacanumber[1]) * 0.1
        thickness = int(nacanumber[2:]) * 0.01

    else:
        if not all(params_specified):
            raise ValueError(
                "Must specify either `name` or all three (`max_camber`, `camber_loc`, `thickness`) parameters.")

    # Referencing https://en.wikipedia.org/wiki/NACA_airfoil#Equation_for_a_cambered_4-digit_NACA_airfoil
    # from here on out

    # Make uncambered coordinates
    x_t = np.cosspace(0, 1, n_points_per_side)  # Generate some cosine-spaced points
    y_t = 5 * thickness * (
            + 0.2969 * x_t ** 0.5
            - 0.1260 * x_t
            - 0.3516 * x_t ** 2
            + 0.2843 * x_t ** 3
            - 0.1015 * x_t ** 4  # 0.1015 is original, #0.1036 for sharp TE
    )

    if camber_loc == 0:
        camber_loc = 0.5  # prevents divide by zero errors for things like naca0012's.

    # Get camber
    y_c = np.where(
        x_t <= camber_loc,
        max_camber / camber_loc ** 2 * (2 * camber_loc * x_t - x_t ** 2),
        max_camber / (1 - camber_loc) ** 2 * ((1 - 2 * camber_loc) + 2 * camber_loc * x_t - x_t ** 2)
    )

    # Get camber slope
    dycdx = np.where(
        x_t <= camber_loc,
        2 * max_camber / camber_loc ** 2 * (camber_loc - x_t),
        2 * max_camber / (1 - camber_loc) ** 2 * (camber_loc - x_t)
    )
    theta = np.arctan(dycdx)

    # Combine everything
    x_U = x_t - y_t * np.sin(theta)
    x_L = x_t + y_t * np.sin(theta)
    y_U = y_c + y_t * np.cos(theta)
    y_L = y_c - y_t * np.cos(theta)

    # Flip upper surface so it's back to front
    x_U, y_U = x_U[::-1], y_U[::-1]

    # Trim 1 point from lower surface so there's no overlap
    x_L, y_L = x_L[1:], y_L[1:]

    x = np.concatenate((x_U, x_L))
    y = np.concatenate((y_U, y_L))

    return stack_coordinates(x, y)


def get_kulfan_coordinates(
        lower_weights: np.ndarray = -0.2 * np.ones(5),
        upper_weights: np.ndarray = 0.2 * np.ones(5),
        enforce_continuous_LE_radius: bool = True,
        TE_thickness: float = 0.,
        n_points_per_side: int = _default_n_points_per_side,
        N1: float = 0.5,
        N2: float = 1.0,
) -> np.ndarray:
    """
    Calculates the coordinates of a Kulfan (CST) airfoil.
    To make a Kulfan (CST) airfoil, use the following syntax:

    >>> import aerosandbox as asb
    >>> asb.Airfoil("My Airfoil Name", coordinates=asb.get_kulfan_coordinates(*args))

    More on Kulfan (CST) airfoils: http://brendakulfan.com/docs/CST2.pdf
    Notes on N1, N2 (shape factor) combinations:
        * 0.5, 1: Conventional airfoil
        * 0.5, 0.5: Elliptic airfoil
        * 1, 1: Biconvex airfoil
        * 0.75, 0.75: Sears-Haack body (radius distribution)
        * 0.75, 0.25: Low-drag projectile
        * 1, 0.001: Cone or wedge airfoil
        * 0.001, 0.001: Rectangle, circular duct, or circular rod.
    :param lower_weights: An iterable of the Kulfan weights to use for the lower surface.
    :param upper_weights: An iterable of the Kulfan weights to use for the upper surface.
    :param enforce_continuous_LE_radius: Enforces a continuous leading-edge radius by discarding the first lower weight.
    :param TE_thickness: The trailing edge thickness to add, in terms of y/c.
    :param n_points_per_side: The number of points to discretize with.
    :param N1: LE shape factor; see above.
    :param N2: TE shape factor; see above.
    :return: The coordinates of the airfoil as a Nx2 array.
    """

    if enforce_continuous_LE_radius:
        lower_weights[0] = -1 * upper_weights[0]

    x_lower = np.cosspace(0, 1, n_points_per_side)
    x_upper = x_lower[::-1]

    x_lower = x_lower[1:]  # Trim off the nose coordinate so there are no duplicates

    def shape(w, x):
        # Class function
        C = x ** N1 * (1 - x) ** N2

        # Shape function (Bernstein polynomials)
        n = len(w) - 1  # Order of Bernstein polynomials

        K = comb(n, np.arange(n + 1))  # Bernstein polynomial coefficients

        S_matrix = (
                w * K * np.expand_dims(x, 1) ** np.arange(n + 1) *
                np.expand_dims(1 - x, 1) ** (n - np.arange(n + 1))
        )  # Polynomial coefficient * weight matrix
        # S = np.sum(S_matrix, axis=1)
        S = np.array([np.sum(S_matrix[i, :]) for i in range(S_matrix.shape[0])])

        # Calculate y output
        y = C * S
        return y

    y_lower = shape(lower_weights, x_lower)
    y_upper = shape(upper_weights, x_upper)

    # TE thickness
    y_lower -= x_lower * TE_thickness / 2
    y_upper += x_upper * TE_thickness / 2

    x = np.concatenate([x_upper, x_lower])
    y = np.concatenate([y_upper, y_lower])
    coordinates = np.vstack((x, y)).T

    return coordinates


def get_coordinates_from_raw_dat(
        raw_text: List[str]
) -> np.ndarray:
    """
    Returns a Nx2 ndarray of airfoil coordinates from the raw text of a airfoil *.dat file.

    Args:

        raw_text: A list of strings, where each string is one line of the *.dat file. One good way to get this input
            is to read the file via the `with open(file, "r") as file:`, `file.readlines()` interface.

    Returns: A Nx2 ndarray of airfoil coordinates [x, y].

    """
    raw_coordinates = []

    def is_number(s: str) -> bool:
        # Determines whether a string is representable as a float
        try:
            float(s)
        except ValueError:
            return False
        return True

    def parse_line(line: str) -> Optional[List[float]]:
        # Given a single line of a `*.dat` file, tries to parse it into a list of two floats [x, y].
        # If not possible, returns None.
        line_split = re.split(r'[;|,|\s|\t]', line)
        line_items = [s for s in line_split
                      if s != "" and is_number(s)
                      ]
        if len(line_items) == 2 and all([is_number(i) for i in line_items]):
            return line_items
        else:
            return None

    for line in raw_text:
        parsed_line = parse_line(line)
        if parsed_line is not None:
            raw_coordinates.append(parsed_line)

    if len(raw_coordinates) == 0:
        raise ValueError("Could not read any coordinates from the `raw_text` input!")

    coordinates = np.array(raw_coordinates, dtype=float)

    return coordinates


def get_file_coordinates(
        filepath: Union[str, os.PathLike]
):
    possible_errors = (FileNotFoundError, UnicodeDecodeError)

    if isinstance(filepath, np.ndarray):
        raise TypeError("`filepath` should be a string or os.PathLike object.")

    try:
        with open(filepath, "r") as f:
            raw_text = f.readlines()
    except possible_errors as e:
        try:
            with open(f"{filepath}.dat", "r") as f:
                raw_text = f.readlines()
        except possible_errors as e:
            raise FileNotFoundError(
                f" Neither '{filepath}' nor '{filepath}.dat' were found and readable."
            ) from e

    try:
        return get_coordinates_from_raw_dat(raw_text)
    except ValueError:
        raise ValueError("File was found, but could not read any coordinates!")


def get_UIUC_coordinates(
        name: str = 'dae11'
) -> np.ndarray:
    """
    Returns the coordinates of a specified airfoil in the UIUC airfoil database.
    Args:
        name: Name of the airfoil to retrieve from the UIUC database.

    Returns: The coordinates of the airfoil as a Nx2 ndarray [x, y]
    """

    name = name.lower().strip()

    import importlib.resources
    from aerosandbox.geometry.airfoil import airfoil_database

    try:
        with importlib.resources.open_text(airfoil_database, name) as f:
            raw_text = f.readlines()
    except FileNotFoundError as e:
        try:
            with importlib.resources.open_text(airfoil_database, name + '.dat') as f:
                raw_text = f.readlines()
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"Neither '{name}' nor '{name}.dat' were found in the UIUC airfoil database."
            ) from e

    return get_coordinates_from_raw_dat(raw_text)
