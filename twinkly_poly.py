#!/usr/bin/env python3

"""
This is a NodeServer for Twinkly written by automationgeek (Jean-Francois Tremblay)
based on the NodeServer template for Polyglot v2 written in Python2/3 by Einstein.42 (James Milne) milne.james@gmail.com
"""

import udi_interface
import hashlib
import asyncio
import warnings 
import time
import json
import sys
from copy import deepcopy
from twinkly_client import TwinklyClient
from aiohttp import ClientSession, ClientTimeout

LOGGER = udi_interface.LOGGER
SERVERDATA = json.load(open('server.json'))
VERSION = SERVERDATA['credits'][0]['version']

def get_profile_info(logger):
    pvf = 'profile/version.txt'
    try:
        with open(pvf) as f:
            pv = f.read().replace('\n', '')
    except Exception as err:
        logger.error('get_profile_info: failed to read  file {0}: {1}'.format(pvf,err), exc_info=True)
        pv = 0
    f.close()
    return { 'version': pv }

class Controller(udi_interface.Node):

    def __init__(self, polyglot, primary, address, name):
        super(Controller, self).__init__(polyglot, primary, address, name)
        self.poly = polyglot
        self.name = 'Twinkly'
        self.queryON = False
        self.host = ""
        self.hb = 0

        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.CUSTOMPARAMS, self.parameterHandler)
        polyglot.subscribe(polyglot.POLL, self.poll)

        polyglot.ready()
        polyglot.addNode(self)

    def parameterHandler(self, params):
        self.poly.Notices.clear()
        try:
            if 'host' in params:
                self.host = params['host']
            else:
                self.host = ""

            if self.host == "" :
                self.poly.Notices['cfg'] = 'Twinkly requires the "host" parameter to be specified.'
                LOGGER.error('Twinkly requires \'host\' parameters to be specified in custom configuration.')
                return False
            else:
                self.discover()
                
        except Exception as ex:
            LOGGER.error('Error starting Twinkly NodeServer: %s', str(ex))

    def start(self):
        LOGGER.info('Started Twinkly for v3 NodeServer version %s', str(VERSION))
        self.setDriver('ST', 0)
           
    def poll(self, polltype):
        if 'shortPoll' in polltype:
            self.setDriver('ST', 1)
            for node in self.poly.nodes():
                if  node.queryON == True :
                    node.update()
        else:
            self.heartbeat()
        
    def query(self):
        for node in self.poly.nodes():
            node.reportDrivers()

    def heartbeat(self):
        LOGGER.debug('heartbeat: hb={}'.format(self.hb))
        if self.hb == 0:
            self.reportCmd("DON",2)
            self.hb = 1
        else:
            self.reportCmd("DOF",2)
            self.hb = 0

    def discover(self, *args, **kwargs):
        count = 1
        for host in self.host.split(','):
            uniq_name = "t" + "_" + host.replace(".","") + "_" + str(count)
            myhash =  str(int(hashlib.md5(uniq_name.encode('utf8')).hexdigest(), 16) % (10 ** 8))
            if not self.poly.getNode(myhash):
                self.poly.addNode(TwinklyLight(self.poly,self.address, myhash , uniq_name, host ))
            count = count + 1

    def delete(self):
        LOGGER.info('Deleting Twinkly')

    id = 'controller'
    commands = {
        'QUERY': query,
        'DISCOVER': discover,
    }
    drivers = [{'driver': 'ST', 'value': 1, 'uom': 2}]

class TwinklyLight(udi_interface.Node):

    def __init__(self, controller, primary, address, name, host):

        super(TwinklyLight, self).__init__(controller, primary, address, name)
        self.queryON = True
        self.myHost = host

        controller.subscribe(controller.START, self.start, address)

    def start(self):
        self.update()

    def query(self):
        self.reportDrivers()

    def setOn(self, command):
        try:
            asyncio.run(self._turnOn())
            self.setDriver('ST', 100)
        except Exception as ex:
            LOGGER.error('setOn: %s', str(ex))
        
    def setOff(self, command):
        try :
            asyncio.run(self._turnOff())
            self.setDriver('ST', 0)
        except Exception as ex:
            LOGGER.error('setOff: %s', str(ex))
    
    def setBrightness(self, command):
        try:
            asyncio.run(self._setBrightness(int(command.get('value'))))
            self.setDriver('GV1', int(command.get('value')))
        except Exception as ex:
            LOGGER.error('setBrightness: %s', str(ex))
        
    def update(self):
        try :
            if ( asyncio.run(self._isOn()) ) :
                self.setDriver('ST', 100)
            else :
                self.setDriver('ST', 0)
            self.setDriver('GV1', asyncio.run(self._getBri()))
        except Exception as ex :
            LOGGER.error('update: %s', str(ex))

    async def _isOn(self) : 
        cs = ClientSession(raise_for_status=True, timeout=ClientTimeout(total=3))
        isOn = await TwinklyClient(self.myHost,cs).get_is_on()
        await cs.close()
        return isOn
        
    async def _getBri(self) : 
        cs = ClientSession(raise_for_status=True, timeout=ClientTimeout(total=3))
        intBri = await TwinklyClient(self.myHost,cs).get_brightness()
        await cs.close()
        return intBri
    
    async def _turnOff(self) :
        cs = ClientSession(raise_for_status=True, timeout=ClientTimeout(total=3))
        tc = await TwinklyClient(self.myHost,cs).set_is_on(False)
        await cs.close()
        
    async def _turnOn(self) :
        cs = ClientSession(raise_for_status=True, timeout=ClientTimeout(total=3))
        tc = await TwinklyClient(self.myHost,cs).set_is_on(True)
        await cs.close()
        
    async def _setBrightness(self,bri) :
        cs = ClientSession(raise_for_status=True, timeout=ClientTimeout(total=3))
        await TwinklyClient(self.myHost,cs).set_brightness(bri)
        await cs.close()
            
    drivers = [{'driver': 'ST', 'value': 0, 'uom': 78},
               {'driver': 'GV1', 'value': 0, 'uom': 51}]

    id = 'TWINKLY_LIGHT'
    commands = {
                    'DON': setOn,
                    'DOF': setOff,
                    'SET_BRI': setBrightness
                }

if __name__ == "__main__":
    try:
        polyglot = udi_interface.Interface([])
        polyglot.start()
        polyglot.updateProfile()
        polyglot.setCustomParamsDoc()
        Controller(polyglot, 'controller', 'controller', 'TwinklyNodeServer')
        polyglot.runForever()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
