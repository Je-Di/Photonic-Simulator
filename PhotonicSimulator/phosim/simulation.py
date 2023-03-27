from __future__ import annotations
from collections import OrderedDict

from .components import Component, Waveguide, PortType
from .data_types import OpticalPower


class PhotonicSimulation:
    def __init__(self):
        self._components = OrderedDict()
        self._observers = dict()
        self._dependencies_resolved = False

    def add_component(self, component: Component, name=None) -> tuple[str, Component]:
        if not name:
            name = self._first_available_component_name(component.description)
        if name in self._components.keys():
            raise RuntimeError(f"Component with name {name} already exists!")

        self._components[name] = component
        self._dependencies_resolved = False

        return name, component

    def connect(self, source: Component | str, target: Component | str,
                port_type: PortType = PortType.OPTICAL, source_port_id: int = 0,
                target_port_id: int = 0, waveguide: Waveguide = None):
        if isinstance(source, str):
            source = self._components[source]
        if isinstance(target, str):
            target = self._components[target]

        source.connect_to(target, port_type, source_port_id, target_port_id, waveguide)

        if waveguide:
            self.add_component(waveguide)

    def create_observer(self, target: Component | str, port_type: PortType, port_id: int = 0,
                        name: str = None):
        if not name:
            name = self._first_available_observer_name()
        if name in self._observers.keys():
            raise RuntimeError(f"Observer with name {name} already exists!")
        observer = Observer(target, port_type, port_id)
        self._observers[name] = observer

        return name, observer

    def update(self):
        if not self._dependencies_resolved:
            self._resolve_dependencies()

        for component in self._components.values():
            component.update()

        for observer in self._observers.values():
            observer.record()

    def _resolve_dependencies(self):
        """ Sorts the components based on their input / output dependencies.

        After sorting, the outputs of a component do not rely on the output of a component later in
        the dict, i.e. the components can be updated in the given order.

        The algorithm has not been optimized for speed as it only needs to be run once whenever
        the simulation topology changes.
        """
        current_index = 0
        iterated_componentes = 0
        while current_index != len(self._components):
            unresolved_components = list(self._components.values())[current_index:]
            # Raise an error if all unresolved components were iterated without finding one
            # without dependencies.
            if iterated_componentes == len(unresolved_components):
                raise RuntimeError("Error creating update order: Could not find component without "
                                   "dependencies. This can be caused by circular references.")
            (name, component) = list(self._components.items())[current_index]
            has_dependencies = False
            input_connections = component.connections_in
            for port_type in PortType:
                for connection in input_connections[port_type]:
                    if connection.component in unresolved_components:
                        has_dependencies = True
            if has_dependencies:
                self._components.move_to_end(name)
                iterated_componentes += 1
            else:
                current_index += 1
                iterated_componentes = 0

        self._dependencies_resolved = True

    @property
    def observer_data(self) -> list[list[OpticalPower]] | list[list[float]] | list[list[int]]:
        return [observer.data for observer in self._observers]

    def _first_available_name(self, description: str, dictionary: dict) -> str:
        """ Find the first available key in dict according to the scheme "'description' #". """
        index = 0
        while True:
            name = description + " " + str(index)
            if name not in dictionary.keys():
                break
            index += 1
        return name

    def _first_available_component_name(self, description: str):
        return self._first_available_name(description, self._components)

    def _first_available_observer_name(self):
        return self._first_available_name("Observer", self._observers)


class Observer:
    def __init__(self, target: Component, port_type: PortType, port_id: int = 0):
        self._data = []
        self._port_type = port_type
        self._target = target
        self._port_id = port_id

    def reset(self):
        self._data = []

    def record(self):
        self._data.append(self._target.get_output(self._port_type, self._port_id))

    @property
    def data(self) -> list[OpticalPower] | list[float] | list[int]:
        return self._data

    @property
    def target(self):
        return self._target

    @target.setter
    def target(self, target):
        self._target = target

    @property
    def port_id(self):
        return self._port_id

    @port_id.setter
    def port_id(self, port_id):
        self._port_id = port_id
