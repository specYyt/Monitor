#_*_coding:utf-8_*_
__author__ = 'Alex Li'


import os,sys,subprocess
# import commands
import re

def collect():
    filter_keys = ['Manufacturer','Serial Number','Product Name','UUID','Wake-up Type'] #[制造商，序列号，产品名，UUID，醒来的类型]
    raw_data = {}

    for key in filter_keys:
        try:
            cmd_res = subprocess.getoutput("sudo dmidecode -t system|grep '%s'" %key)
            cmd_res = cmd_res.strip() #取到命令执行结果

            res_to_list = cmd_res.split(':')
            if len(res_to_list)> 1:#判断 Product Name: VMware Virtual Platform 第二段长度是否大于1，若长度大于一，则说明是我们想要的内容
                raw_data[key] = res_to_list[1].strip() #将取到的内容存到字典中
            else:
                raw_data[key] = -1
        except Exception as e:
            print(e)
            raw_data[key] = -2 #用-2表示命令的执行结果出错

    data = {"asset_type":'server'}
    data['manufactory'] = raw_data['Manufacturer']
    data['sn'] = raw_data['Serial Number']
    data['model'] = raw_data['Product Name']
    data['uuid'] = raw_data['UUID']
    data['wake_up_type'] = raw_data['Wake-up Type']

    data.update(cpuinfo())
    data.update(osinfo())
    data.update(raminfo())
    #data.update(nicinfo()) 因为只能取到物理网卡的信息，这里将其注释掉
    #data.update(diskinfo()) 虚拟机有问题
    return data

def cpuinfo():
    base_cmd = 'cat /proc/cpuinfo'

    raw_data = {
        'cpu_model' : "%s |grep 'model name' |head -1 " % base_cmd,
        'cpu_count' :  "%s |grep  'processor'|wc -l " % base_cmd,  #逻辑cpu数
        'cpu_core_count' : "%s |grep 'cpu cores' |awk -F: '{SUM +=$2} END {print SUM}'" % base_cmd, #统计出CPU的核数
    }

    for k,cmd in raw_data.items():
        try:
            cmd_res = subprocess.getoutput(cmd)
            raw_data[k] = cmd_res.strip()

        except ValueError as e:
            print(e)
    data = {
        "cpu_count" : raw_data["cpu_count"],
        "cpu_core_count": raw_data["cpu_core_count"]
        }
    cpu_model = raw_data["cpu_model"].split(":")
    if len(cpu_model) >1:
        data["cpu_model"] = cpu_model[1].strip()
    else:
        data["cpu_model"] = -1
    return data

def osinfo():
    distributor = subprocess.getoutput(" lsb_release -a|grep 'Distributor ID'").split(":") #['Distributor ID', '\tRedHatEnterpriseServer']
    release  = subprocess.getoutput(" lsb_release -a|grep Description").split(":") #['Description', '\tRed Hat Enterprise Linux Server release 7.0 (Maipo)']
    data_dic ={
        "os_distribution": distributor[1].strip() if len(distributor)>1 else None,
        "os_release":release[1].strip() if len(release)>1 else None,
        "os_type": "linux",
    }
    return data_dic

def nicinfo():
    '''
    返回网卡信息，这里必须是实体机才有效
    :return:
    '''
    raw_data = subprocess.getoutput("ifconfig -a")
    raw_data= raw_data.split("\n") #用换行分隔取到的内容，保存为一个大的列表

    nic_dic = {}
    next_ip_line = False
    last_mac_addr = None
    for line in raw_data:
        if next_ip_line:
            next_ip_line = False
            nic_name = last_mac_addr.split()[0]
            mac_addr = last_mac_addr.split("HWaddr")[1].strip()
            raw_ip_addr = line.split("inet addr:")
            raw_bcast = line.split("Bcast:")
            raw_netmask = line.split("Mask:")
            if len(raw_ip_addr) > 1: #has addr
                ip_addr = raw_ip_addr[1].split()[0]
                network = raw_bcast[1].split()[0]
                netmask =raw_netmask[1].split()[0]
            else:
                ip_addr = None
                network = None
                netmask = None
            if mac_addr not in nic_dic:
                nic_dic[mac_addr] = {'name': nic_name,
                                     'macaddress': mac_addr,
                                     'netmask': netmask,
                                     'network': network,
                                     'bonding': 0,
                                     'model': 'unknown',
                                     'ipaddress': ip_addr,
                                     }
            else: #mac already exist , must be boding address
                if '%s_bonding_addr' %(mac_addr) not in nic_dic:
                    random_mac_addr = '%s_bonding_addr' %(mac_addr)
                else:
                    random_mac_addr = '%s_bonding_addr2' %(mac_addr)

                nic_dic[random_mac_addr] = {'name': nic_name,
                                     'macaddress':random_mac_addr,
                                     'netmask': netmask,
                                     'network': network,
                                     'bonding': 1,
                                     'model': 'unknown',
                                     'ipaddress': ip_addr,
                                     }

        if "HWaddr" in line:
            #print line
            next_ip_line = True
            last_mac_addr = line


    nic_list= []
    for k,v in nic_dic.items():
        nic_list.append(v)

    return {'nic':nic_list}

def raminfo():
    raw_data = subprocess.getoutput("sudo dmidecode -t 17")
    raw_list = raw_data.split("\n")
    raw_ram_list = [] #用来存放整个的输出结果
    item_list = [] #用来存放单个的 Memory Device
    for line in raw_list:
        if line.startswith("Memory Device"):  #是新的内存设备的开始
            raw_ram_list.append(item_list)
            item_list =[]
        else:
            item_list.append(line.strip())

    ram_list = []
    for item in raw_ram_list:
        item_ram_size = 0
        ram_item_to_dic = {}
        for i in item: #循环 item_list
            data = i.split(":")
            if len(data) ==2: #例如===》Size: No Module Installed
                key,v = data
                if key == 'Size':
                    if  v.strip() != "No Module Installed":
                        ram_item_to_dic['capacity'] =  v.split()[0].strip() #例如 ：Size: 2048 MB
                        item_ram_size = int(v.split()[0]) #取到单个内存的大小
                    else:
                        ram_item_to_dic['capacity'] =  0
                if key == 'Type':
                    ram_item_to_dic['model'] =  v.strip()
                if key == 'Manufacturer':
                    ram_item_to_dic['manufactory'] =  v.strip()
                if key == 'Serial Number':
                    ram_item_to_dic['sn'] =  v.strip()
                if key == 'Asset Tag':
                    ram_item_to_dic['asset_tag'] =  v.strip()
                if key == 'Locator': #槽位号
                    ram_item_to_dic['slot'] =  v.strip()

        if item_ram_size == 0:  # 如果此槽位的内存为0，说明为空，没有插内存条
            pass
        else:
            ram_list.append(ram_item_to_dic)
    raw_total_size = subprocess.getoutput("cat /proc/meminfo|grep MemTotal ").split(":") #取到内存总大小 ===》['MemTotal', '        1870764 kB']
    ram_data = {'ram':ram_list} #每个插有内存条的槽位的内存数据
    if len(raw_total_size) == 2: #['MemTotal', '        1870764 kB'] ===》数据正确
        total_mb_size = int(raw_total_size[1].split()[0]) / 1024
        ram_data['ram_size'] =  total_mb_size
    return ram_data

def diskinfo():
    obj = DiskPlugin()
    return obj.linux()

class DiskPlugin(object):
    def linux(self):
        result = {'physical_disk_driver':[]}

        try:
            script_path = os.path.dirname(os.path.abspath(__file__))
            shell_command = "sudo %s/MegaCli  -PDList -aALL" % script_path
            output = subprocess.getstatusoutput(shell_command)
            result['physical_disk_driver'] = self.parse(output[1]) #取到硬盘信息
        except Exception as e:
            result['error'] = e
        return result

    def parse(self,content):
        '''
        解析shell命令返回结果
        :param content: shell 命令结果
        :return:解析后的结果
        '''
        response = []
        result = []
        for row_line in content.split("\n\n\n\n"):
            result.append(row_line)
        for item in result:
            temp_dict = {}
            for row in item.split('\n'):
                if not row.strip():
                    continue
                if len(row.split(':')) != 2:
                    continue
                key,value = row.split(':')
                name =self.mega_patter_match(key);
                if name:
                    if key == 'Raw Size':
                        raw_size = re.search('(\d+\.\d+)',value.strip())
                        if raw_size:

                            temp_dict[name] = raw_size.group()
                        else:
                            raw_size = '0'
                    else:
                        temp_dict[name] = value.strip()

            if temp_dict:
                response.append(temp_dict)
        return response

    def mega_patter_match(self,needle):
        grep_pattern = {'Slot':'slot', 'Raw Size':'capacity', 'Inquiry':'model', 'PD Type':'iface_type'}
        for key,value in grep_pattern.items():
            if needle.startswith(key):
                return value
        return False

if __name__=="__main__":
    print(DiskPlugin().linux())