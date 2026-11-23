"""Values returned by 05_climate.js (run in a browser console on open-meteo.com; the shells could not reach the API).
HI = Huglin index per year, k = 1.04 (44-46°N). RAIN = ERA5 annual precipitation (mm). SUM = 1991-2020 (n) and 2015-2024 (r) means.
The second half of this file averages the three Saint-Joseph points and writes climate_stats.json.
"""
yrs=list(range(1991,2025))
HI={
"Gigondas":[2142,2016,2017,2233,2034,1875,2157,2129,2266,2218,2128,2127,2681,2225,2305,2463,2282,2092,2470,2171,2405,2393,2049,2230,2429,2326,2505,2491,2499,2471,2208,2733,2592,2294],
"SJ south":[1764,1682,1624,1845,1610,1477,1792,1709,1796,1784,1691,1689,2393,1827,1898,2007,1847,1658,2096,1804,2015,1885,1683,1796,2104,1851,2128,2281,2091,2124,1696,2321,2130,1881],
"SJ centre":[1753,1684,1615,1825,1595,1468,1791,1694,1790,1767,1668,1660,2381,1801,1878,1974,1810,1639,2072,1785,1988,1841,1667,1779,2082,1833,2099,2260,2060,2100,1674,2286,2088,1844],
"SJ north":[1792,1771,1675,1854,1619,1520,1872,1734,1847,1807,1684,1672,2394,1803,1896,1966,1809,1671,2074,1783,2008,1844,1703,1809,2101,1870,2080,2258,2063,2186,1753,2348,2152,1916]}
RAIN={
"Gigondas":[464,817,961,856,664,1110,614,594,789,884,724,907,781,604,496,589,528,938,693,801,608,683,936,913,660,692,420,1071,852,549,762,686,616,997],
"SJ south":[690,1069,1110,1042,852,1084,750,779,1085,1059,964,1047,853,864,665,797,708,1228,775,885,815,923,1112,1101,796,840,554,925,966,720,971,843,865,1162],
"SJ centre":[795,1179,1190,1162,994,1158,820,901,1260,1145,1101,1098,842,999,818,894,862,1322,871,936,922,1085,1182,1151,877,955,680,983,1069,840,1137,944,1059,1260],
"SJ north":[760,1101,1093,1122,965,1091,746,857,1140,1033,1023,1035,775,923,814,824,890,1167,817,869,838,1039,1114,1051,831,913,692,911,955,784,1091,876,977,1179]}
SUM={ # from Open-Meteo JS (era5_land temps at vine median elevation; era5 precip)
"Gigondas":{"n":{"huglin":2261,"gdd10":1823,"rain_yr":740,"rain_apr_sep":339,"spring_frost_days":0.2,"jul_tmax":29.4,"jul_tmin":17.6,"days35_summer":3.3},"r":{"huglin":2455,"gdd10":2025,"rain_yr":731,"rain_apr_sep":325,"spring_frost_days":0.3,"jul_tmax":31.1,"jul_tmin":19.1,"days35_summer":8.1}},
"SJ south":{"n":{"huglin":1865,"gdd10":1453,"rain_yr":902,"rain_apr_sep":461,"spring_frost_days":0.8,"jul_tmax":26.6,"jul_tmin":15.8,"days35_summer":1.4},"r":{"huglin":2061,"gdd10":1647,"rain_yr":864,"rain_apr_sep":419,"spring_frost_days":1.0,"jul_tmax":28.2,"jul_tmin":17.0,"days35_summer":4.0}},
"SJ centre":{"n":{"huglin":1845,"gdd10":1436,"rain_yr":1003,"rain_apr_sep":531,"spring_frost_days":0.7,"jul_tmax":26.3,"jul_tmin":15.7,"days35_summer":1.0},"r":{"huglin":2033,"gdd10":1621,"rain_yr":980,"rain_apr_sep":499,"spring_frost_days":1.3,"jul_tmax":27.8,"jul_tmin":16.9,"days35_summer":2.7}},
"SJ north":{"n":{"huglin":1872,"gdd10":1482,"rain_yr":939,"rain_apr_sep":492,"spring_frost_days":0.5,"jul_tmax":26.2,"jul_tmin":15.9,"days35_summer":1.1},"r":{"huglin":2073,"gdd10":1682,"rain_yr":921,"rain_apr_sep":463,"spring_frost_days":1.1,"jul_tmax":27.8,"jul_tmin":17.2,"days35_summer":3.2}}}

if __name__ == "__main__":
    import json
    import numpy as np
    y = np.array(yrs)
    sj = np.mean([HI[k] for k in HI if k.startswith("SJ")], axis=0)
    avg = lambda key, p: round(float(np.mean([SUM[k][p][key] for k in SUM if k.startswith("SJ")])), 1)
    clim = {"Saint-Joseph": {p: {key: avg(key, p) for key in SUM["Gigondas"]["n"]} for p in "nr"},
            "Gigondas": SUM["Gigondas"],
            "hi_by_year": {"years": yrs, "Saint-Joseph": sj.round().tolist(), "Gigondas": HI["Gigondas"]}}
    json.dump(clim, open("climate_stats.json", "w"), indent=1)
