# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['luna',
 'luna.gateware',
 'luna.gateware.applets',
 'luna.gateware.architecture',
 'luna.gateware.debug',
 'luna.gateware.interface',
 'luna.gateware.interface.gateware_phy',
 'luna.gateware.interface.serdes_phy',
 'luna.gateware.interface.serdes_phy.backends',
 'luna.gateware.platform',
 'luna.gateware.stream',
 'luna.gateware.test',
 'luna.gateware.test.contrib',
 'luna.gateware.usb',
 'luna.gateware.usb.devices',
 'luna.gateware.usb.request',
 'luna.gateware.usb.usb2',
 'luna.gateware.usb.usb2.endpoints',
 'luna.gateware.usb.usb2.interfaces',
 'luna.gateware.utils']

package_data = \
{'': ['*']}

install_requires = \
['apollo-fpga>=0.0.4,<0.0.5',
 'libusb1>=1.9.2,<2.0.0',
 'nmigen @ git+https://github.com/nmigen/nmigen.git@master',
 'nmigen-boards @ git+https://github.com/nmigen/nmigen-boards.git@master',
 'nmigen-soc @ git+https://github.com/nmigen/nmigen-soc.git@master',
 'pyserial>=3.5,<4.0',
 'pyusb>=1.1.1,<2.0.0',
 'pyvcd>=0.2.4,<0.3.0',
 'usb-protocol @ git+https://github.com/usb-tools/python-usb-protocol@master',
 'ziglang>=0.8.0,<0.9.0']

setup_kwargs = {
    'name': 'luna',
    'version': '0.1.0.dev0',
    'description': 'USB2 highspeed core, written in nMigen',
    'long_description': None,
    'author': 'Katherine Temkin',
    'author_email': 'k@ktemkin.com',
    'maintainer': None,
    'maintainer_email': None,
    'url': None,
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)
