from __future__ import annotations
import math
from abc import ABC, abstractmethod
from enum import Enum, auto
from dataclasses import dataclass
from typing import NamedTuple
import warnings

from .data_types import OpticalPower, IntRange, ConnectionEndpoint
from .utilities import factor_to_db, db_to_factor


@dataclass
class ComponentTypeAttributes:
    """ Holds the attributes of a specific component type (e.g. laser, EOM, ...). """
    description: str
    # A set of strings with the implemented optical loss types, e.g. "propagation", "insertion", ...
    optical_losses_types: set[str]
    # The minimum and maximum number of in-/output ports that an instance of this type can have for
    # every port type.
    ports_in_ranges: dict[str: IntRange]
    ports_out_ranges: dict[str: IntRange]


class PortType(Enum):
    OPTICAL = auto()
    ANALOG = auto()
    DIGITAL = auto()


class PortsCount(NamedTuple):
    """ Stores the number of ports for all three types. """
    optical: int
    analog: int
    digital: int

    def __getitem__(self, port_type: PortType) -> int:
        if port_type == PortType.OPTICAL:
            return self.optical
        elif port_type == PortType.ANALOG:
            return self.analog
        elif port_type == PortType.DIGITAL:
            return self.digital
        else:
            raise IndexError("Invalid 'port_type'.")


class Component(ABC):
    """ The base class for all components in a simulation.

    A component can have optical, analog and digital input and output ports.
    Optical ports transmit light intensities per wavelength of data type OpticalPower.
    Analog ports transmit analog voltages of data type float.
    Digital ports transmit digital data of data type int.

    The update() function calculates the output per port based on the inputs. Children of this class
    must overwrite the update function.

    Children must also overwrite the component type attributes. See class 'ComponentTypeAttributes'
    for details.
    """
    _component_type_attributes = None

    def __init__(self, ports_in_count: PortsCount, ports_out_count: PortsCount,
                 optical_losses_db: dict[str: float] = None):
        # Ensure that the component type attributes are set.
        if self._component_type_attributes is None:
            raise RuntimeError("Instantiating component that does not have type attributes.")
        # Ensure that the actual number of ports is within the allowed range.
        for port_type in PortType:
            if not self._component_type_attributes.ports_in_ranges[port_type].in_range(
                    ports_in_count[port_type]):
                raise ValueError(f"The component does not allow {ports_in_count[port_type]} "
                                 f"ports of type {port_type}.")
        # Ensure that all the required types of optical losses are implemented
        for optical_losses_type in self._component_type_attributes.optical_losses_types:
            if not optical_losses_type in optical_losses_db.keys():
                warnings.warn(f"Optical loss type {optical_losses_type} not specified, "
                              "setting to 0.0.")
                optical_losses_db[optical_losses_type] = 0.0

        self._connections_in = dict()
        self._connections_out = dict()
        self._connections_in[PortType.OPTICAL] = [None] * ports_in_count.optical
        self._connections_in[PortType.ANALOG] = [None] * ports_in_count.analog
        self._connections_in[PortType.DIGITAL] = [None] * ports_in_count.digital
        self._connections_out[PortType.OPTICAL] = [None] * ports_out_count.optical
        self._connections_out[PortType.ANALOG] = [None] * ports_out_count.analog
        self._connections_out[PortType.DIGITAL] = [None] * ports_out_count.digital

        self._output = dict()
        self._output[PortType.OPTICAL] = [OpticalPower()] * ports_out_count.optical
        self._output[PortType.ANALOG] = [0.0] * ports_out_count.analog
        self._output[PortType.DIGITAL] = [0] * ports_out_count.digital

        if optical_losses_db:
            self._losses_db = optical_losses_db
            self._losses_factor = db_to_factor(optical_losses_db)
        else:
            self._losses_db = None
            self._losses_factor = None

    def connect_to(self, target: Component, port_type: PortType = PortType.OPTICAL,
                   source_port_id: int = 0, target_port_id: int = 0,
                   waveguide: Waveguide = None) -> None:
        """ Connect an output port to an input port of the target component.

        :param target: The target component to which the connection is made.
        :param port_type: The type of the connection (optical, analog, digital).
        :param source_port_id: The index of the output port.
        :param target_port_id: The index of the target's input port.
        :param waveguide: Establish the connection via the given waveguide if != None.
                          Only valid for optical connections.
        """
        if waveguide and port_type == PortType.OPTICAL:
            self.connect_to(waveguide)
            waveguide.connect_to(target, target_port_id=target_port_id)

        else:
            if waveguide:
                warnings.warn("Waveguide is not None for non-optical port.")

            if source_port_id >= len(self._connections_out[port_type]):
                raise RuntimeError(f"Output port {source_port_id} exceeds number of output ports "
                                   f"({len(self._connections_out[port_type])}) at source {self}.")
            if self._connections_out[port_type][source_port_id]:
                Warning(f"Overwriting connection at output port {source_port_id} of source {self}.")
            self._connections_out[port_type][source_port_id] = \
                ConnectionEndpoint(target, target_port_id)

            if target_port_id >= len(target._connections_in[port_type]):
                raise RuntimeError(f"Input port {target_port_id} exceeds number of input ports "
                                   f"({len(self._connections_in[port_type])}) at target {target}.")
            if target.get_input_connection(port_type, target_port_id):
                Warning(
                    f"Overwriting connection at input port {target_port_id} of target {target}.")
            target._connections_in[port_type][target_port_id] = \
                ConnectionEndpoint(self, source_port_id)

    @property
    def connections_in(self) -> dict[PortType: list[ConnectionEndpoint]]:
        return self._connections_in

    def get_input_connection(self, port_type: PortType, port_id: int) -> ConnectionEndpoint:
        """ Return connection at specified input port."""
        return self._connections_in[port_type][port_id]

    def get_output_connection(self, port_type: PortType, port_id: int) -> ConnectionEndpoint:
        """ Return connection at specified output port."""
        return self._connections_out[port_type][port_id]

    def get_input(self, port_type: PortType, port_id: int, copy: bool = True) -> \
            OpticalPower | float | int:
        """ Get the data present at a specific input port.

        :param port_type: The port type.
        :param port_id: The port index.
        :param copy: If true, a copy of the data is made before returning it.
        :return: Data that is present at the input due to the connection to another component.
        """
        connection = self._connections_in[port_type][port_id]
        if connection:
            ret = connection.component.get_output(port_type, connection.port_id)
            if copy and hasattr(ret, "copy"):
                return ret.copy()
            return ret
        else:
            raise RuntimeError(f"Port {port_id} of component {self} is not connected.")

    def get_output(self, port_type: PortType, port_id: int, copy: bool = False) -> \
            OpticalPower | float | int:
        """ Get the data of a specific output port.

        :param port_type: The port type.
        :param port_id: The port index.
        :param copy: If true, a copy of the data is made before returning it.
        :return: The output at the specified port.
        """
        output = self._output[port_type][port_id]
        if copy and hasattr(output, "copy"):
            return output.copy()
        return output

    @abstractmethod
    def update(self):
        return

    @property
    def description(self):
        return self._component_type_attributes.description

    @property
    def losses_db(self):
        return self._losses_db

    @losses_db.setter
    def losses_db(self, losses):
        self._losses_db = losses
        self._losses_factor = db_to_factor(losses)

    @property
    def losses_factor(self):
        return self._losses_factor

    @losses_factor.setter
    def losses_factor(self, losses):
        self._losses_factor = losses
        self._losses_db = factor_to_db(losses)


class Eom(Component):
    """ An electro-optical modulator.

    The electro-optical modulator has one optical input, one optical output and an analog
    modulation value. The incoming light is attenuated according to the function
    A(v) = sin^2(v / v_pi * pi)
    """
    _component_type_attributes = ComponentTypeAttributes(
        description="EOM",
        optical_losses_types={"insertion"},
        ports_in_ranges={PortType.OPTICAL: IntRange(1, 1),
                         PortType.ANALOG: IntRange(1, 1),
                         PortType.DIGITAL: IntRange(0, 0)},
        ports_out_ranges={PortType.OPTICAL: IntRange(1, 1),
                          PortType.ANALOG: IntRange(0, 0),
                          PortType.DIGITAL: IntRange(0, 0)})

    def __init__(self, v_pi, losses_db):
        super().__init__(PortsCount(1, 1, 0), PortsCount(1, 0, 0), losses_db)
        self._v_pi = v_pi

    def update(self):
        modulation_voltage = self.get_input(PortType.ANALOG, 0)
        self._output[PortType.OPTICAL][0] = self.get_input(PortType.OPTICAL, 0, copy=True)
        self._output[PortType.OPTICAL][0] *= \
            math.sin(modulation_voltage / self._v_pi) ** 2 * self.losses_factor["insertion"]

    @property
    def v_pi(self):
        return self._v_pi

    @v_pi.setter
    def v_pi(self, v_pi):
        self._v_pi = v_pi


class Splitter(Component):
    _component_type_attributes = ComponentTypeAttributes(
        description="Splitter",
        optical_losses_types={"insertion"},
        ports_in_ranges={PortType.OPTICAL: IntRange(1, 1),
                         PortType.ANALOG: IntRange(0, 0),
                         PortType.DIGITAL: IntRange(0, 0)},
        ports_out_ranges={PortType.OPTICAL: IntRange(1, -1),
                          PortType.ANALOG: IntRange(0, 0),
                          PortType.DIGITAL: IntRange(0, 0)})

    def __init__(self, size, losses_db):
        super().__init__(PortsCount(1, 0, 0), PortsCount(size, 0, 0), losses_db)

    def update(self):
        self._output[PortType.OPTICAL] = \
            [self.get_input(PortType.OPTICAL, 0) / len(self._connections_out[PortType.OPTICAL])
             * self.losses_factor["insertion"] for _ in self._connections_out[PortType.OPTICAL]]

    @property
    def size(self):
        return len(self._connections_out[PortType.OPTICAL])


class Demux(Component):
    _component_type_attributes = ComponentTypeAttributes(
        description="Demux",
        optical_losses_types={"insertion"},
        ports_in_ranges={PortType.OPTICAL: IntRange(1, 1),
                         PortType.ANALOG: IntRange(0, 0),
                         PortType.DIGITAL: IntRange(0, 0)},
        ports_out_ranges={PortType.OPTICAL: IntRange(1, -1),
                          PortType.ANALOG: IntRange(0, 0),
                          PortType.DIGITAL: IntRange(0, 0)})

    def __init__(self, wavelengths, losses_db):
        super().__init__(PortsCount(1, 0, 0), PortsCount(len(wavelengths), 0, 0), losses_db)
        self._wavelengths = wavelengths

    def update(self):
        input_light = self.get_input(PortType.OPTICAL, 0)
        for port, wavelength in enumerate(self._wavelengths):
            self._output[PortType.OPTICAL][port] = \
                input_light[wavelength] * self.losses_factor["insertion"]

    @property
    def size(self):
        return len(self._wavelengths)

    @property
    def wavelengths(self):
        return self._wavelengths


class Mux(Component):
    _component_type_attributes = ComponentTypeAttributes(
        description="Mux",
        optical_losses_types={"insertion"},
        ports_in_ranges={PortType.OPTICAL: IntRange(1, -1),
                         PortType.ANALOG: IntRange(0, 0),
                         PortType.DIGITAL: IntRange(0, 0)},
        ports_out_ranges={PortType.OPTICAL: IntRange(1, 1),
                          PortType.ANALOG: IntRange(0, 0),
                          PortType.DIGITAL: IntRange(0, 0)})

    def __init__(self, input_count, losses_db):
        super().__init__(PortsCount(input_count, 0, 0), PortsCount(1, 0, 0), losses_db)


    def update(self):
        self._output[PortType.OPTICAL][0] = OpticalPower()
        for index in range(len(self.connections_in)):
            input_light = self.get_input(PortType.OPTICAL, index, copy=False)
            self._output[PortType.OPTICAL][0] += input_light * self.losses_factor["insertion"]

    @property
    def input_count(self):
        return len(self.connections_in)


class Photodetector(Component):
    _component_type_attributes = ComponentTypeAttributes(
        description="Photodetector",
        optical_losses_types=set(),
        ports_in_ranges={PortType.OPTICAL: IntRange(1, 1),
                         PortType.ANALOG: IntRange(1, 1),
                         PortType.DIGITAL: IntRange(0, 0)},
        ports_out_ranges={PortType.OPTICAL: IntRange(1, 1),
                          PortType.ANALOG: IntRange(0, 0),
                          PortType.DIGITAL: IntRange(0, 0)})

    def __init__(self, gain):
        super().__init__(PortsCount(1, 0, 0), PortsCount(0, 1, 0))
        self._gain = gain

    @property
    def gain(self):
        return self._gain

    @gain.setter
    def gain(self, gain):
        self._gain = gain

    def update(self):
        self._output[PortType.ANALOG][0] = \
            sum(self.get_input(PortType.OPTICAL, 0).values()) * self.gain


class Laser(Component):
    _component_type_attributes = ComponentTypeAttributes(
        description="Laser",
        optical_losses_types=set(),
        ports_in_ranges={PortType.OPTICAL: IntRange(0, 0),
                         PortType.ANALOG: IntRange(0, 0),
                         PortType.DIGITAL: IntRange(0, 0)},
        ports_out_ranges={PortType.OPTICAL: IntRange(1, 1),
                          PortType.ANALOG: IntRange(0, 0),
                          PortType.DIGITAL: IntRange(0, 0)})

    def __init__(self, wavelength, power):
        super().__init__(PortsCount(0, 0, 0), PortsCount(1, 0, 0))
        self._wavelength = wavelength
        self._power = power
        self._update_output()

    def update(self):
        # Laser does not require update.
        pass

    @property
    def wavelength(self):
        return self._wavelength

    @wavelength.setter
    def wavelength(self, wavelength):
        self._wavelength = wavelength
        self._update_output()

    @property
    def power(self):
        return self._power

    @power.setter
    def power(self, power):
        self._power = power
        self._update_output()

    def _update_output(self):
        self._output[PortType.OPTICAL][0] = OpticalPower({self._wavelength: self._power})


class VoltageSource(Component):
    _component_type_attributes = ComponentTypeAttributes(
        description="Voltage Source",
        optical_losses_types=set(),
        ports_in_ranges={PortType.OPTICAL: IntRange(0, 0),
                         PortType.ANALOG: IntRange(0, 0),
                         PortType.DIGITAL: IntRange(0, 0)},
        ports_out_ranges={PortType.OPTICAL: IntRange(0, 0),
                          PortType.ANALOG: IntRange(1, 1),
                          PortType.DIGITAL: IntRange(0, 0)})

    def __init__(self, voltage=0.0):
        super().__init__(PortsCount(0, 0, 0), PortsCount(0, 1, 0))
        self._voltage = voltage
        self._update_output()

    def update(self):
        # Voltage source does not require update.
        pass

    @property
    def voltage(self):
        return self._voltage

    @voltage.setter
    def voltage(self, voltage):
        self._voltage = voltage
        self._update_output()

    def _update_output(self):
        self._output[PortType.ANALOG][0] = self._voltage


class Waveguide(Component):
    _component_type_attributes = ComponentTypeAttributes(
        description="Waveguide",
        optical_losses_types=("propagation", ),
        ports_in_ranges={PortType.OPTICAL: IntRange(1, 1),
                         PortType.ANALOG: IntRange(0, 0),
                         PortType.DIGITAL: IntRange(0, 0)},
        ports_out_ranges={PortType.OPTICAL: IntRange(1, 1),
                          PortType.ANALOG: IntRange(0, 0),
                          PortType.DIGITAL: IntRange(0, 0)})

    def __init__(self, length_um, losses_db):
        super().__init__(PortsCount(1, 0, 0), PortsCount(1, 0, 0), losses_db)
        self._length_um = length_um

    def update(self):
        self._output[PortType.OPTICAL][0] = self.get_input(PortType.OPTICAL, 0) * \
                                            self.losses_factor["propagation"]

    @property
    def length_um(self):
        return self._length_um

    @length_um.setter
    def length_um(self, length_um):
        self._length_um = length_um
