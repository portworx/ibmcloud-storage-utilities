#!/usr/bin/env python3.6

import sys
import json
import time
from os.path import expanduser
import urllib.request
import SoftLayer
from pprint import pprint as pp

class IKS_clusters:

    def __init__(self, IAMToken, cluster=None, region=None):
        self._token = ""
        self._hdrs = ""
        self._region = []
        self._cluster = []
        self._token = IAMToken

        self._hdrs={'Content-Type': 'application/json', 'Authorization' : self._token }

        if not region:
            try:
                request = urllib.request.Request(url="https://containers.bluemix.net/v1/regions", headers=self._hdrs)
                contents = json.load(urllib.request.urlopen(request))
            except:
                raise Exception ("Failed `v1/regions`.  Probably bad Token = " + self._token)
            for c in contents['regions']:
                  self._region.append(c['name'])
        else:
            self._region = [ region ]

        for r in self._region:
             self._hdrs = {'Content-Type': 'application/json', 'X-Region' : r, 'Authorization' : self._token }
             try:
                 if not cluster:
                      request = urllib.request.Request(url="https://containers.bluemix.net/v1/clusters", headers=self._hdrs)
                      cl_contents = json.load(urllib.request.urlopen(request))
                 else:
                      request = urllib.request.Request(url="https://containers.bluemix.net/v1/clusters/" + cluster, headers=self._hdrs)
                      cl_contents =  [ json.load(urllib.request.urlopen(request)) ]
                 for cl in cl_contents:
                     cls = {}
                     cls['name'] = cl['name']
                     cls['region'] = r
                     cls['workers'] = []
                     try:
                          request = urllib.request.Request(url="https://containers.bluemix.net/v1/clusters/" + cl['name'] + "/workers" , headers=self._hdrs)
                          w_contents = json.load(urllib.request.urlopen(request))
                     except:
                          print ("Can't access Cloud API for workers for cluster: ", cl['name'])
                     for w in w_contents:
                          cls['workers'].append (w)
                     self._cluster.append(cls)
             except urllib.error.HTTPError as e:
                   if e.code == 401:
                        raise Exception("HTTP 401 Authentication problems. Please do a 'bx login', and make sure your IAMToken is valid")
             except:
                 # Assume looking for a specific cluster across all regions, and it's not in *this* one
                 pass

    def list(self):
         return self._cluster




class IKS_vols:
    """
       IKS volume object and access functions
    """

    def __init__(self):
         try:
             self._BSmgr = SoftLayer.BlockStorageManager(SoftLayer.Client())
             self._Nmgr  = SoftLayer.managers.network.NetworkManager(SoftLayer.Client())
         except:
             raise Exception("Cannot initialize SoftLayer Client")

    def get_vol(self, volID):
         self.detail = {}
         self.acls   = []
         #
         # Retriev ACLs, if any
         #
         try:
             lba = self._BSmgr.get_block_volume_access_list(volID)
             for a in lba['allowedIpAddresses']:
                 acl = {}
                 acl['iqn']      = lba['allowedIpAddresses'][0]['allowedHost']['name']
                 acl['username'] =  lba['allowedIpAddresses'][0]['allowedHost']['credential']['username']
                 acl['password'] = lba['allowedIpAddresses'][0]['allowedHost']['credential']['password']
                 acl['hostIP']   = lba['allowedIpAddresses'][0]['ipAddress']
                 self.acls.append(acl)
         except:
             raise Exception("Failed ordering Block Volume from SoftLayer")
         # 
         # Retrieve volume details
         #
         try:
             lv = self._BSmgr.get_block_volume_details(volID)
             self.detail['targetIP']   = lv['serviceResourceBackendIpAddress']
             self.detail['lunID']      = lv['lunId']
             self.detail['capacityGb'] = lv['capacityGb']
             return (self)
         except:
             raise Exception("Failed ordering Block Volume from SoftLayer")

    def listall(self):
        volIDs = []
        try:
            result = self._BSmgr.list_block_volumes(mask='billingItem.orderItem.order')
            for i in result:
                  if 'billingItem' in i:
                      volIDs.append(i['id'])
            return (volIDs)
        except SoftLayer.exceptions.SoftLayerAPIError:
            raise Exception("Authentication Problem.  Are SL_API_KEY and SL_USERNAME set?")

    def order_vol(self, storage_type, location, size, tier_level, iops, service_offering):
        try:
            result = self._BSmgr.order_block_volume(storage_type=storage_type, 
                              location=location, size=size, tier_level=tier_level, 
                              iops=iops, os_type='LINUX',
                              service_offering=service_offering)
            return (result['orderId'])
        except:
            raise Exception("Failed ordering Block Volume from SoftLayer")

    def wait4_vol(self, orderId):
        while True:
             try:
                 result = self._BSmgr.list_block_volumes(mask='billingItem.orderItem.order')
                 for i in result:
                      if 'billingItem' in i:
                            if i['billingItem']['orderItem']['order']['id'] == orderId:
                                  return (i['id'])
                 print ("No volume yet ... for orderID : ", orderId)
                 time.sleep(8)
             except:
                 raise Exception("Failed ordering Block Volume from SoftLayer")

    #
    # Return unique ID for IP Address
    # (required for authorize_host)
    #
    def get_ip_id (self, ipaddr):
        result = self._Nmgr.ip_lookup(ipaddr)
        return result['id']

    def authorize_host_vol(self, volId, ipAddr):
        ip_id = self.get_ip_id (ipAddr)
        ip_ids = [ ip_id ]
        while True:
            try:
                 print ("Granting access to volume: %s for HostIP: %s" % (volId, ipAddr))
                 access = self._BSmgr.authorize_host_to_volume(volume_id=volId, ip_address_ids=ip_ids)
                 return access
            except:
                 print ("Vol %s is not yet ready (ipAddr : %s )" % (volId, ipAddr))
                 print ("    ip_ids = ", ip_ids)
                 time.sleep (10)
