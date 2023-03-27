import matplotlib.pyplot as plt

from phosim.components import (Laser, Photodetector, Eom, VoltageSource, Waveguide, Splitter,
                               PortType)
from phosim.simulation import PhotonicSimulation


if __name__ == '__main__':
    multiplier = PhotonicSimulation()
    # Add a laser with wavelength 1550 nm and 1 mW power.
    _, laser = multiplier.add_component(Laser(1550, 1e-3), "Laser")
    # Add electro-optical modulators with v_pi = 3 [V] and 2 db insertion loss.
    _, input_eom = multiplier.add_component(Eom(3, {"insertion": 2}), "Input EOM")
    weight_eoms = [
        multiplier.add_component(Eom(3, {"insertion": 2}), f"Input EOM {i}")[1]
        for i in range(2)]
    # Add voltage sources to drive the EOMs.
    _, input_eom_vs = multiplier.add_component(VoltageSource())
    weight_eom_vs = [multiplier.add_component(VoltageSource())[1]
                     for _ in weight_eoms]
    # Add a splitter with 2 output ports and 1 dB insertion loss.
    _, splitter = multiplier.add_component(Splitter(2, {"insertion": 1}), "Splitter")
    # Add two photodetectors.
    photodetectors = [
        multiplier.add_component(Photodetector(1), f"Photodetector {i}")[1] for i in range(2)]
    # Create an observer for each photodetector.
    observers = [multiplier.create_observer(photodetector, PortType.ANALOG, 0)[1]
                 for photodetector in photodetectors]

    # Connect the laser output to the EOM input via a newly created waveguide.
    # Components can be addressed by name.
    waveguide = Waveguide(100, {"propagation": 0})
    multiplier.connect("Laser", "Input EOM", waveguide=waveguide)
    # Directly connect the eom output to the splitter input without a waveguide in between.
    # Components can also be addressed by reference.
    multiplier.connect(input_eom, splitter)
    # Connect the splitter outputs to the photodetectors via the second layer of EOMs.
    for i, photodetector in enumerate(photodetectors):
        multiplier.connect("Splitter", weight_eoms[i], source_port_id=i)
        multiplier.connect(weight_eoms[i], photodetector)
    # Connect the voltage sources to the analog inputs of the corresponding EOMs.
    multiplier.connect(input_eom_vs, input_eom, PortType.ANALOG)
    for i, eom in enumerate(weight_eoms):
        multiplier.connect(weight_eom_vs[i], eom, PortType.ANALOG)

    # Run N steps. A data point is stored per observer in every step.
    step_count = 300
    for i in range(step_count):
        multiplier.update()
        input_eom_vs.voltage += 0.1
        weight_eom_vs[0].voltage = 1.5
        weight_eom_vs[1].voltage += 0.03

    fig, ax = plt.subplots()
    ax.plot(observers[0].data, 'b', label="PD 0")
    ax.plot(observers[1].data, 'r', label="PD 1")
    ax.set(xlabel="Iteration", ylabel="Detector Voltage [V]")
    ax.legend()
    plt.show()
