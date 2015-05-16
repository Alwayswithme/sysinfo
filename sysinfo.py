#!/bin/python3
#
# Author     :  Ye Jinchang
# Date       :  2015-05-15 12:13:38
# Title      :  sysinfo

import subprocess
import os
import sys
import re

def check_permission():
    euid = os.geteuid()
    if euid != 0:
        print('Script not started as root. Running sudo..')
        args = ['sudo', sys.executable] + sys.argv + [os.environ]
        # the next line replaces the currently-running process with the sudo
        os.execlpe('sudo', *args)

def sh(cmd, in_shell=False, get_str=True):
    output = subprocess.check_output(cmd, shell=in_shell)
    if get_str:
        return str(output, 'utf-8')
    return output

class Hwinfo:
    @classmethod
    def product(cls):
        cmd = 'dmidecode -s system-product-name | head -1'
        output = sh(cmd, True)
        return Info('Product', output.strip())
    
    @classmethod
    def distro(cls):
        cmd = 'cat /etc/os-release | egrep "(^NAME=|^VERSION=)"'
        output = sh(cmd, True)
        list = output.split('\n')
        name = list[0].split('=')[1]
        version = list[1].split('=')[1].replace('"', '')
        return Info('Distro', ' '.join((name, version)))
    
    @classmethod
    def kernel(cls):
        cmd = ['uname', '-o', '-r']
        output = sh(cmd)
        return Info('Kernel', output.strip())
    
    @classmethod
    def processor(cls):
        cmd = 'dmidecode -s processor-version | head -1'
        output = sh(cmd, True)
        return Info('Processor', output.strip())
    
    @classmethod
    def baseboard(cls):
        vendor = sh('cat /sys/devices/virtual/dmi/id/board_vendor', True)
        name = sh('cat /sys/devices/virtual/dmi/id/board_name', True)
        chipset = sh('lspci | grep ISA | sed -e "s/.*: //" -e "s/LPC.*//"', True)
        desc = vendor + name + chipset
        return Info('BaseBoard', desc.replace('\n', ' ', 2).strip())

    def __init__(self):
        infos = []
        infos.append(Hwinfo.product())
        infos.append(Hwinfo.distro())
        infos.append(Hwinfo.kernel())
        infos.append(Hwinfo.processor())
        infos.append(Hwinfo.baseboard())
        infos.append(Rom())
        infos.append(Memory())
        infos.append(Disk())
        infos.append(OnboardDevice())
        self.info_list = infos
    
    def __str__(self):
        return ''.join([i.msg() for i in self.info_list])

class Info:
    fieldWidth = 10
    spaces = '│──'
    # represent any hardware information
    def __init__(self, name, desc):
        self.name = name
        self.desc = desc
        self.subInfo = []

    # generate the message to print
    def msg(self):
        msg = []
        spaces = ' ' * (Info.fieldWidth - len(self.name))
        main_msg = '{0}{1}: {2}\n'.format(self.name, spaces, self.desc)
        msg.append(main_msg)
        sub_msg = [ self.indent_subInfo(i) for i in self.subInfo if i]
        if sub_msg:
            sub_msg[-1] = sub_msg[-1].replace('│', '└')
        return ''.join(msg + sub_msg)
    
    def add_subInfo(self, subInfo):
        self.subInfo.append(subInfo)
    
    def indent_subInfo(self, line):
        return Info.spaces + line
    
    def __str__(self):
        return  '"name": {0}, "description": {1}'.format(self.name, self.desc)

class Rom(Info):
    def __init__(self):
        self.rom_list = self.roms()
        Info.__init__(self, 'Rom', self.get_desc())
    def get_desc(self):
        roms = [self.transform(i) for i in self.rom_list]
        roms_msg = ['{0} {1}'.format(i['VENDOR'], i['MODEL']) for i in roms]
        return ' '.join(roms_msg)
    
    def transform(self, line):
        rom = {}
        for line in re.split(r'(?<=") ', line):
            if '=' in line:
                key, value = line.split('=')
                if key in 'VENDOR' or key in 'MODEL':
                    rom[key] = value.replace('"', '').strip()
        return rom
    def roms(self):
        cmd = """lsblk -dP -o VENDOR,TYPE,MODEL | grep 'TYPE="rom"'"""
        output = sh(cmd, True)
        rom_list = [x for x in output.split('\n') if x]
        return rom_list
    
class OnboardDevice(Info):
    def __init__(self):
        Info.__init__(self, 'Onboard', '')
        self.ob_devices = self.onboard_device()
        info = [self.ob_to_str(i) for i in self.ob_devices]
        for i in info:
            self.add_subInfo(i);

    def onboard_device(self):
        cmd = ['dmidecode', '-t', '41']
        parsing = False
        ob_list = []
        splitter = ': '
        attrs = ['Reference Designation', 'Type']
        with subprocess.Popen(cmd, stdout=subprocess.PIPE,
                              bufsize = 1, universal_newlines = True) as p:
            for i in p.stdout:
                line = i.strip()
                if not parsing and line == 'Onboard Device':
                    parsing = True
                    ob = {}
                if parsing and splitter in line:
                    (key, value) = line.split(splitter, 1)
                    if key in attrs:
                        ob[key] = value
                elif parsing and not line:
                    parsing = False
                    ob_list.append(ob)
        return ob_list

    def ob_to_str(self, ob):
        tvalue = ob['Type']
        desvalue = ob['Reference Designation']
        ret = '{0}: {1}\n'.format(tvalue, desvalue)
        return ret

class Disk(Info):
    def __init__(self):
        self.disks = self.disk_list()
        Info.__init__(self, 'Disks', ' '.join(self.disk_list()))
        self.details = self.disks_detail(self.disks)
        detail_strs = [ self.extract_disk_detail(i) for i in self.details]
        for i in detail_strs:
            self.add_subInfo(i)
    
    # query how many disk
    def disk_list(self):
        sds = sh('ls -1d /dev/sd[a-z]', in_shell=True)
        sd_list = [x for x in sds.split('\n') if x]
        return sd_list

    def disks_detail(self, sd_list):
        cmd = ['smartctl', '-i']
        parsing = False
        splitter = ':'
        disk_list = []
        attrs = ['Model Family', 'Device Model', 'User Capacity']
        try:
            for i in sd_list:
                new_cmd = cmd[:]
                new_cmd.append(i)
                with subprocess.Popen(new_cmd, stdout=subprocess.PIPE,
                                      bufsize = 1, universal_newlines=True) as p:
                    for j in p.stdout:
                        line = j.strip()
                        if not parsing and 'START OF INFORMATION' in line:
                            parsing = True
                            disk = {}
                        if parsing and splitter in line:
                            key, value = line.split(splitter, 1)
                            value = value.strip()
                            if key in 'Model Family':
                                disk['model'] = value
                            elif key in 'Device Model':
                                disk['device'] = value
                            elif key in 'User Capacity':
                                p = re.compile('\[.*\]')
                                m = p.search(value)
                                disk['capacity'] = m.group()
                        elif parsing and not line:
                            parsing = False
                            disk['node'] = i
                            disk_list.append(disk)
        except Exception:
            pass
        return disk_list

    def extract_disk_detail(self, disk):
        line = '{node}: {device} {capacity}\n'.format(node=disk['node'], device=disk['device'],
            capacity=disk['capacity'])
        return line


class Memory(Info):
    def __init__(self):
        self.memory = self.memory()
        Info.__init__(self, 'Memory', self.get_desc(self.memory))
        detail_strs = [ self.extract_mem_detail(i) for i in self.memory]
        for i in detail_strs:
            self.add_subInfo(i)

    def memory(self):
        cmd = ['dmidecode', '-t', 'memory']
        parsing = False
        splitter = ': '
        attrs = ['Size', 'Type', 'Speed', 'Manufacturer', 'Locator']
        mem_list = []
        with subprocess.Popen(cmd, stdout=subprocess.PIPE,
                              bufsize = 1, universal_newlines = True) as p:
            for i in p.stdout:
                line = i.strip()
                if not parsing and line == 'Memory Device':
                    parsing = True
                    mem = {}
                if parsing and splitter in line:
                    (key, value) = line.split(splitter, 1)
                    if key in attrs:
                        mem[key] = value

                # read a empty, end the parsing
                elif parsing and not line:
                    parsing = False
                    mem_list.append(mem)
        return mem_list

    def extract_mem_detail(self, mem):
        # maybe no memory in this slot
        if 'Unknown' in mem['Type'] and 'No Module Installed' in mem['Size']:
            return ''
        line = '{slot}: {manufa} {type} {speed}\n'.format(
            slot=mem['Locator'], manufa=mem['Manufacturer'],
            type=mem['Type'], speed=mem['Speed'])
        return line

    def get_desc(self, mem_list):
        mem_size = [self.conv_memsize(i['Size']) for i in mem_list]
        total = sum(mem_size)
        return '{0} MB Total'.format(total)
    
    def conv_memsize(self, size_str):
        (size, unit) = size_str.split(' ', 1);
        try:
            return int(size)
        except ValueError:
            return 0
        
check_permission()
system_info = Hwinfo()
print(system_info)
