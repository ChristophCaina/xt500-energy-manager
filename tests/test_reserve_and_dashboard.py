"""Offline checks of production paths with HA interface doubles."""
import ast
import asyncio
import inspect
import logging
from pathlib import Path
from types import SimpleNamespace as S
import unittest
from unittest.mock import AsyncMock, Mock, call
import test_xt500_controller as prod
c=prod.controller
const=__import__('sys').modules[prod.PACKAGE+'.const']
ROOT=Path(__file__).parents[1]/'custom_components/xt500_energy_manager'
class HAError(Exception):pass

def methods(*names):
    tree=ast.parse((ROOT/'runtime.py').read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='XT500Runtime')
    body=[n for n in cls.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
    for n in body:n.decorator_list=[]
    ns=vars(const).copy();ns.update(math=__import__("math"),Any=object,HomeAssistantError=HAError,datetime=prod.datetime,UTC=prod.UTC,dt_util=S(now=lambda:prod.datetime.now(prod.UTC)),monotonic=lambda:10)
    exec(compile(ast.Module(body=body,type_ignores=[]),'runtime.py','exec'),ns)
    return ns

class ReserveTest(unittest.TestCase):
    def test_default_and_locks(self):
        self.assertFalse(const.DEFAULT_SETTINGS['reserve_enabled'])
        ns=methods('reserve_hold_active','discharge_hold_active')
        for enabled in (False,True):
            for device in (False,True):
                for reserve in (False,True):
                    r=S(settings={'reserve_enabled':enabled},_low_soc_hold=device,_reserve_hold=reserve)
                    r.reserve_hold_active=ns['reserve_hold_active'](r)
                    self.assertEqual(ns['discharge_hold_active'](r),device or (enabled and reserve))
    def test_release_tracks_original_hysteresis(self):
        fn=methods('reserve_release_soc')['reserve_release_soc']
        r=S(settings={'reserve_soc':40,'soc_hysteresis':3})
        self.assertEqual(fn(r),43)
        r.settings['soc_hysteresis']=5;self.assertEqual(fn(r),45)
        r.settings['reserve_soc']=99;self.assertEqual(fn(r),100)
    def test_validation_storage_and_restart(self):
        fn=methods('async_set_setting')['async_set_setting']
        r=S(settings=dict(const.DEFAULT_SETTINGS),_reserve_hold=False,discharge_override_active=False,_store=S(async_delay_save=Mock()),async_calculate=Mock())
        for value in (0,100,float('nan'),float('inf')):
            with self.assertRaises(HAError):fn(r,'reserve_soc',value)
        fn(r,'reserve_soc',60)
        self.assertIsNone(r._reserve_hold)
        self.assertEqual(r.settings['minimum_soc'],const.DEFAULT_SETTINGS['minimum_soc'])
        self.assertTrue(c.update_discharge_hold(current_hold=None,soc=62,minimum_soc=60,hysteresis=3))
        r.discharge_override_active=True
        with self.assertRaises(HAError):fn(r,'reserve_enabled',True)
        self.assertFalse(r.settings['reserve_enabled'])
    def test_runtime_latch_follows_original_hysteresis(self):
        tree=ast.parse((ROOT/'runtime.py').read_text())
        reserve=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Attribute) and t.attr=='_reserve_hold' for t in n.targets))
        ns=vars(const).copy();ns['update_discharge_hold']=c.update_discharge_hold
        r=S(settings={'reserve_enabled':True,'reserve_soc':40},_reserve_hold=None)
        for soc,hyst,expected in ((41,3,True),(43,3,False),(40,3,True),(44,5,True),(45,5,False)):
            ns.update(self=r,values={const.CONF_SOC_ENTITY:soc},hysteresis=hyst)
            exec(compile(ast.Module(body=[reserve],type_ignores=[]),'runtime.py','exec'),ns)
            self.assertEqual(r._reserve_hold,expected)
        r.settings['reserve_enabled']=False
        exec(compile(ast.Module(body=[reserve],type_ignores=[]),'runtime.py','exec'),ns)
        self.assertIsNone(r._reserve_hold)
    def test_no_one_shot_escape(self):
        r=S(regulation_enabled=True,data_valid=True,settings={'reserve_enabled':True})
        with self.assertRaisesRegex(HAError,'Reserve'):asyncio.run(methods('async_release_discharge_once')['async_release_discharge_once'](r))
    def test_stop_bypasses_ramp_and_keeps_charge_limit(self):
        states={'gs':600,'is':800,'sa':100}
        r=S(control_ready=True,result=S(recommended_grid_setpoint=0,recommended_inverter_setpoint=100),reserve_hold_active=True,
            entry=S(data={const.CONF_GRID_SETPOINT_ENTITY:'gs',const.CONF_INVERTER_SETPOINT_ENTITY:'is',const.CONF_MAX_CHARGE_SOC_ENTITY:'sa'}),desired_charge_limit=100,
            _limited_entity_target=lambda e,t,m:states[e]-20,_quantized_entity_target=lambda e,t:t,_float_state=lambda e:states[e],
            hass=S(states=S(get=lambda e:S(attributes={'step':1}))),_async_set_number_resilient=AsyncMock(),_notify=Mock())
        asyncio.run(methods('_async_apply_control_result')['_async_apply_control_result'](r,20))
        self.assertEqual(r._async_set_number_resilient.await_args_list,[call('is',100),call('gs',0)])

    def test_all_charge_sources_respect_reserve(self):
        for source in ('manual','cycle_manual','cycle_automatic','tariff'):
            for mode in ('grid_charge','pv_surplus','pv_priority','pv_and_grid'):
                for pv in (0,2000):
                    result=c.calculate_control(prod.ControllerTest().input(soc=40,pv_power=pv),
                        c.ControlSettings(charge_active=True,charge_source=source,charge_mode=mode,
                            target_soc=80,minimum_soc=18,discharge_hold=True))
                    self.assertTrue(result.discharge_blocked,(source,mode,pv))
                    self.assertLessEqual(result.recommended_grid_setpoint,0,(source,mode,pv))
                    self.assertLessEqual(result.recommended_inverter_setpoint,pv,(source,mode,pv))

class Store:
    def __init__(self,hass,version,key):self.hass,self.key=hass,key
    async def async_load(self):return self.hass.saved.get(self.key)
    async def async_save(self,data):self.hass.saved[self.key]=dict(data)
class Dashboard:
    def __init__(self,config=None):self.config=config;self.saves=0
    async def async_load(self,force):
        if self.config is None:raise HAError()
        return self.config
    async def async_save(self,config):self.config=config;self.saves+=1
class Collection:
    loaded=True
    def __init__(self,hass,kind):self.hass=hass;self.kind=kind;self.items=[];self.store=Store(hass,1,kind)
    def async_items(self):return self.items
    async def async_create_item(self,data):
        self.items.append(dict(data))
        if self.kind=='dashboards':self.hass.data['lovelace'].dashboards[data['url_path']]=Dashboard()
        return data
class DashboardTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.hass=S(saved={},data={});self.resources=Collection(self.hass,'resources');self.collection=Collection(self.hass,'dashboards')
        class API:
            def __init__(self,col):self.storage_collection=col
            def ws_list_item(self):pass
        self.hass.data={'lovelace':S(resources=self.resources,dashboards={}), 'websocket_api':{'lovelace/dashboards/list':(API(self.collection).ws_list_item,None)}}
        self.entry=S(data={'auto_dashboard':True});self.notify=Mock()
        tree=ast.parse((ROOT/'dashboard_setup.py').read_text());tree.body=[n for n in tree.body if not isinstance(n,(ast.Import,ast.ImportFrom))]
        for n in ast.walk(tree):
            if isinstance(n,ast.ExceptHandler):n.body=[x for x in n.body if not isinstance(x,ast.ImportFrom)]
        self.ns={'asyncio':asyncio,'inspect':inspect,'logging':logging,'urlsplit':__import__('urllib.parse',fromlist=['urlsplit']).urlsplit,'LOVELACE_DATA':'lovelace','HomeAssistantError':HAError,'ConfigNotFound':HAError,'Store':Store,'CONF_AUTO_DASHBOARD':'auto_dashboard','DOMAIN':'xt500_energy_manager','FRONTEND_URL':const.FRONTEND_URL,'persistent_notification':S(async_create=self.notify,async_dismiss=Mock())}
        exec(compile(tree,'dashboard_setup.py','exec'),self.ns)
    async def run_setup(self):await self.ns['async_ensure_dashboard'](self.hass,self.entry)
    async def test_first_install(self):
        await self.run_setup();self.assertEqual(len(self.resources.items),1)
        self.assertTrue(self.collection.items[0]['show_in_sidebar'])
        self.assertEqual(self.hass.data['lovelace'].dashboards['xt500-energiemanager'].config,{'strategy':{'type':'custom:xt500-energy-manager','dashboard_path':'xt500-energiemanager'}})
        self.notify.assert_not_called()
    async def test_deliberate_delete(self):
        await self.run_setup();self.hass.data['lovelace'].dashboards.clear();await self.run_setup()
        self.assertEqual(len(self.collection.items),1);self.assertFalse(self.hass.data['lovelace'].dashboards)
    async def test_existing_custom_dashboard(self):
        d=Dashboard({'strategy':{'type':'custom:xt500-energy-manager'},'custom':True});self.hass.data['lovelace'].dashboards['custom']=d
        await self.run_setup();self.assertEqual(d.saves,0);self.assertEqual(self.collection.items,[])
    async def test_collision(self):
        d=Dashboard({'views':[{'title':'Private'}]});self.hass.data['lovelace'].dashboards['xt500-energiemanager']=d
        await self.run_setup();self.assertEqual(d.saves,0);self.assertIn('xt500-energiemanager-2',self.hass.data['lovelace'].dashboards)
    async def test_legacy_and_opt_out(self):
        for data in ({},{'auto_dashboard':False}):self.entry.data=data;await self.run_setup()
        self.assertEqual(self.resources.items,[]);self.assertEqual(self.collection.items,[])
    async def test_versioned_resource(self):
        self.resources.items=[{'url':const.FRONTEND_URL+'?v=old','type':'module'}]
        await self.run_setup();self.assertEqual(len(self.resources.items),1)
    async def test_unsupported_ha(self):
        self.hass.data['websocket_api']={}
        with self.assertLogs(self.ns['_LOGGER'],level='ERROR'):await self.run_setup()
        self.notify.assert_called_once();self.assertEqual(self.collection.items,[])
    async def test_concurrent_install(self):
        await asyncio.gather(self.run_setup(),self.run_setup());self.assertEqual(len(self.collection.items),1)
    async def test_failed_save_retries_pending_path(self):
        create=self.collection.async_create_item
        async def fail(data):
            result=await create(data);self.hass.data['lovelace'].dashboards[data['url_path']].async_save=AsyncMock(side_effect=HAError('disk full'));return result
        self.collection.async_create_item=fail
        with self.assertLogs(self.ns['_LOGGER'],level='ERROR'):await self.run_setup()
        d=self.hass.data['lovelace'].dashboards['xt500-energiemanager'];d.async_save=AsyncMock()
        await self.run_setup();self.assertEqual(len(self.collection.items),1);d.async_save.assert_awaited_once()

    async def test_yaml_resources_fail_visibly_without_dashboard_write(self):
        self.hass.data['lovelace'].resources=S(loaded=True,async_items=lambda:[])
        with self.assertLogs(self.ns['_LOGGER'],level='ERROR'):await self.run_setup()
        self.notify.assert_called_once();self.assertEqual(self.collection.items,[])
    async def test_wrong_resource_type_is_preserved_and_reported(self):
        self.resources.items=[{'url':const.FRONTEND_URL,'type':'css'}]
        with self.assertLogs(self.ns['_LOGGER'],level='ERROR'):await self.run_setup()
        self.notify.assert_called_once();self.assertEqual(self.collection.items,[])
        self.assertEqual(self.resources.items[0]['type'],'css')
    async def test_customized_pending_dashboard_is_preserved(self):
        self.hass.saved['xt500_energy_manager.dashboard_setup']={'pending_path':'xt500-energiemanager'}
        d=Dashboard({'views':[{'title':'User change'}]})
        self.hass.data['lovelace'].dashboards['xt500-energiemanager']=d
        await self.run_setup();self.assertEqual(d.saves,0);self.assertEqual(self.collection.items,[])

class StartupAndBypassTest(unittest.TestCase):
    def test_only_first_install_is_disabled(self):
        tree=ast.parse((ROOT/'runtime.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='XT500Runtime')
        start=next(n for n in cls.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='async_start')
        guard=next(n for n in start.body if isinstance(n,ast.If))
        for stored,expected in ((None,False),({'regulation_enabled':True},True)):
            r=S(settings=dict(const.DEFAULT_SETTINGS))
            ns=vars(const).copy();ns.update(self=r,stored=stored,migrated=False)
            exec(compile(ast.Module(body=[guard],type_ignores=[]),'runtime.py','exec'),ns)
            self.assertEqual(r.settings['regulation_enabled'],expected)
    def test_reserve_blocks_full_battery_bypass(self):
        tree=ast.parse((ROOT/'runtime.py').read_text())
        kw=next(n for n in ast.walk(tree) if isinstance(n,ast.keyword) and n.arg=='full_battery_pv_export')
        for hold in (False,True):
            r=S(settings={'full_battery_pv_export':True},reserve_hold_active=hold)
            ns=vars(const).copy();ns['self']=r
            self.assertEqual(eval(compile(ast.Expression(kw.value),'runtime.py','eval'),ns),not hold)
