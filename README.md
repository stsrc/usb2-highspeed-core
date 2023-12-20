# LUNA: an Amaranth HDL library for USB ![Simulation Status](https://github.com/greatscottgadgets/luna/workflows/simulations/badge.svg) [![Documentation Status](https://readthedocs.org/projects/luna/badge/?version=latest)](https://luna.readthedocs.io/en/latest/?badge=latest)

# USB2 High Speed Core
This core is a customization of the [LUNA project](https://github.com/greatscottgadgets/luna),
which is a USB analyzer.

The aim of this project is to strip down the original project to
its USB2 highspeed-capable core which is easy to integrate into your own
FPGA project.

## Notable differences to the LUNA project

* USB MIDI is broken upstream, and is working here
* USB Audio is impossible upstream, because the isochronous endpoints are missing (see below)

This project implements stream based isochronous
in and out endpoints:
* [USBIsochronousInStreamEndpoint](https://github.com/hansfbaier/usb2-highspeed-core/blob/main/luna/gateware/usb/usb2/endpoints/isochronous.py#L219)
* [USBIsochronousOutStreamEndpoint](https://github.com/hansfbaier/usb2-highspeed-core/blob/main/luna/gateware/usb/usb2/endpoints/isochronous.py#L401)

This project includes the following examples:
* [USB2 class compliant high speed audio interface](https://github.com/hansfbaier/usb2-highspeed-core/blob/main/examples/usb2_audio.py)

This project includes the following additional platform files:
* [Terasic/Arrow DECA](https://github.com/hansfbaier/usb2-highspeed-core/blob/main/luna/gateware/platform/arrow_deca.py) configuration tested working on the FPGA

## Project Structure

This project is broken down into several directories:

* `luna` -- the primary LUNA python toolkit; generates gateware and provides USB functionality
  * `luna/gateware` -- the core gateware components for LUNA; and utilities for stitching them together
* `examples` -- simple LUNA-related examples; mostly gateware-targeted, currently
* `docs` -- sources for the LUNA Sphinx documentation
* `applets` -- pre-made gateware applications that provide useful functionality on their own (e.g., are more than examples)

## Project Documentation

LUNA's documentation is captured on [Read the Docs](https://luna.readthedocs.io/en/latest/). Raw documentation sources
are in the `docs` folder.

## Related Projects
* [jt51-synth](https://github.com/hansfbaier/jt51-synth/), a FM synthesizer,
based on jotego's open source implementation of the Yamaha YM2151.
The project uses this core as USB MIDI interface.
* [adat-usb2-audio-interface](https://github.com/hansfbaier/adat-usb2-audio-interface),
an USB2 high speed audio interface with ADAT inputs and outputs
* [deca-usb2-audio-interface](https://github.com/hansfbaier/deca-usb2-audio-interface),
an USB2 high speed audio interface with analog inputs and outputs
* [deca-mandelbrot](https://github.com/hansfbaier/deca-mandelbrot),
  a mandelbrot accelerator connected with a USB2 high speed interface
* [Cynthion](https://github.com/greatscottgadgets/cynthion-hardware): an open source hardware USB test instrument
* [Apollo](https://github.com/greatscottgadgets/apollo): the firmware that runs on Cynthion's debug controller and which is responsible for configuring its FPGA
* [Saturn-V](https://github.com/greatscottgadgets/saturn-v): a DFU bootloader created for Cynthion
* [Packetry](https://github.com/greatscottgadgets/packetry): software for USB analysis
* [Facedancer](https://github.com/greatscottgadgets/facedancer): software to create USB devices in Python
