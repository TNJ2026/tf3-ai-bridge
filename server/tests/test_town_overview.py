import asyncio
from unittest.mock import AsyncMock,Mock
import pytest
from test_facilities import game
from test_town_cargo_supply import SETUP,PASSENGERS
from tf3_mcp.ui_log import validate_build_arguments
SETUP_OVERVIEW=SETUP+PASSENGERS+r'''
OV_STATE={authorityScore=.7,eventFactors={score=.8,reasonToPenalty={Trees=.1}},constructionBoni={xpIncrease=.1},cachedRatings={noise={value=.6,critical=false}}}
local u={NumLinesForHappinessStats=5,externalGetTownState=function()return OV_STATE end,GetRatings=function()return {{key='noise',name='Noise',range={0,1}}}end}
for _,name in ipairs({'getRatingUrbanCare','getRatingCargoDelivery','getRatingNoise','getRatingPollution','getRatingBonuses','getRatingHappiness','getRatingTraffic','getXpFactor','getGrowthLevelMult','getReputation'}) do u[name]=function()return .5 end end
u.getReputationBreakdown=function(f)return f.reasonToPenalty end
u.isMarketingActive=function()return false end
u.getSeveredMainConnections=function()return {} end
u.getRatingDeliveries=function()return {ratingLevelNumber=3,noDeliveries=false}end
u.getNoiseLandUseTypes=function()return {0,1}end
u.getTownEmissionEmitters=function()return {company_vehicles=2}end
u.getTrafficSpeedRating=function()return {.8,{1,2,3}}end
OV_UTIL=u
local old=ug_require
ug_require=function(path)if path=='::/game_mechanics/towns/town_util.tl' then return u end;return old(path)end
local n=api.engine.util.town
n.getTownCapacityUsage=function()return {{used=123,capacity=200}}end
n.getTownReachability=function()return {commercialPrivate=5}end
n.getTownStockCargo=function()return {[6]={1,10}}end
n.getTownNoisePerDistrict=function()return {[0]={2,10}}end
n.getTownEmission=function()return {noise=4,pollution=2,areaSquareKm=1}end
n.getTownEmissionDB=n.getTownEmission
n.getTownHappinessStats=function()return {walking={1,10}}end
n.getTownDeliveriesStats=function()return {[401]={[6]={2,20}}}end
api.util=api.util or {};api.util.getDefaultYearDuration=function()return 1000 end
'''

def test_sections_and_false_are_preserved_without_mutation(game):
 lua,call=game;lua.execute(SETUP_OVERVIEW)
 r=call('get_town_overview',town=100)
 assert r['complete'],r['errors']
 assert set(r['sections'])=={'overview','reputation','delivery','supply','noise','pollution','bonuses','happiness','traffic'}
 assert r['sections']['reputation']['marketingActive']=={'available':True,'value':False,'source':'town_util.isMarketingActive'}
 assert r['sections']['happiness']['stats']['value']['tupleMeaning']=='unhappy,total'
 assert lua.globals().SUBMISSIONS is None

@pytest.mark.parametrize('edit',[
 'OV_UTIL.getRatingNoise=function()return 0/0 end',
 'OV_UTIL.externalGetTownState=function()return nil end',
 'api.engine.util.town.getTownHappinessStats=nil',
 'api.engine.util.town.getTownEmission=function()return {_unavailable="opaque"}end',
])
def test_missing_partial_and_invalid_values_are_unknown(game,edit):
 lua,call=game;lua.execute(SETUP_OVERVIEW+edit);r=call('get_town_overview',town=100)
 assert not r['complete'] and r['errors']
 assert r['sections']['delivery']['deliveries']['available']
 assert lua.globals().SUBMISSIONS is None

def test_rating_helper_cannot_change_native_state(game):
 lua,call=game;lua.execute(SETUP_OVERVIEW+'OV_UTIL.getRatingUrbanCare=function(t,s)s.authorityScore=99;return 1 end')
 call('get_town_overview',town=100);assert lua.globals().OV_STATE.authorityScore==.7

@pytest.mark.parametrize('args',[{}, {'town':True},{'town':-1},{'town':100,'mutate':True}])
def test_validation(args):
 with pytest.raises(ValueError):validate_build_arguments('get_town_overview',args)

def test_public_tool(monkeypatch):
 from tf3_mcp import server
 f=AsyncMock(return_value={'readOnly':True});monkeypatch.setattr(server,'_call',f)
 assert asyncio.run(server.get_town_overview(100))['readOnly']
 f.assert_awaited_once_with('get_town_overview',_engine=True,town=100)

def test_native_userdata_detail_records(game):
 from test_depot_removal import NativeRecord
 lua,call=game;lua.execute(SETUP_OVERVIEW)
 n=lua.globals().api.engine.util.town
 cap=NativeRecord({'used':123,'capacity':200})
 lua.globals().NATIVE_CAP=lua.table_from([cap])
 lua.globals().NATIVE_REACH=NativeRecord(dict(commercialPrivate=1,commercialPublic=2,industrialPrivate=3,industrialPublic=4))
 lua.globals().NATIVE_EMISSION=NativeRecord(dict(noise=4,pollution=2,areaSquareKm=1))
 by=NativeRecord({});by.data={'resident':lua.table_from([1,10]),'nonResident':lua.table_from([2,20])}
 h=NativeRecord({});h.data={k:lua.table_from([1,10]) for k in ['travellingInside','atBuilding','byCar','walking']};h.data.update(travellingTo=by,travellingFrom=by,byLine=lua.table_from([lua.table_from([401,by])]))
 lua.globals().NATIVE_HAPPY=h
 lua.execute('''api.engine.util.town.getTownCapacityUsage=function()return NATIVE_CAP end
 api.engine.util.town.getTownReachability=function()return NATIVE_REACH end
 api.engine.util.town.getTownEmission=function()return NATIVE_EMISSION end
 api.engine.util.town.getTownEmissionDB=function()return NATIVE_EMISSION end
 api.engine.util.town.getTownHappinessStats=function()return NATIVE_HAPPY end''')
 r=call('get_town_overview',town=100);assert r['complete'],r['errors']
 assert r['sections']['happiness']['stats']['value']['data']['byLine'][0][1]['resident']==[1,10]


def test_power_emission_does_not_require_db_area_metadata(game):
 from test_depot_removal import NativeRecord
 lua,call=game;lua.execute(SETUP_OVERVIEW)
 lua.globals().POWER_RECORD=NativeRecord(dict(noise=4,pollution=2))
 lua.execute('api.engine.util.town.getTownEmission=function()return POWER_RECORD end')
 r=call('get_town_overview',town=100)
 assert r['complete'],r['errors']
 assert r['sections']['overview']['emissionsPower']['value']=={'noise':4,'pollution':2}
