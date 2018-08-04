# -*- coding: utf-8 -*-
"""
Created on Sat Aug  4 19:01:12 2018

RSI-AR Model

@author: Lewis YEUNG
"""

# 导入模块
import math
import talib as tl
import pandas as pd
import numpy as np
from datetime import timedelta
import talib

def initialize(context):
    # 初始化此策略
    # 设置要操作的股票池为空，每天需要不停变化股票池
    set_universe([])
    
    # 设置手续费，买入时万分之三，卖出时万分之三加千分之一印花税, 每笔交易最低扣5块钱
    set_commission(PerTrade(buy_cost=0.0003, sell_cost=0.0013, min_cost=5))
    
    # 设置风险基准为沪深300指数
    g.riskbench = '000300.XSHG'

    # 设置基准对比为沪深300指数
    set_benchmark(g.riskbench)

    # 关闭部分log
    #log.set_level('order', 'error')
    
    # 设置真实交易时间
    set_option('use_real_price',True)
    
    # 初始化日期
    g.d_yesterday = ''
    g.d_today = ''
    
    # 定义常量
    g.con_START_DATE = 100 # 股票上市时间限制
    g.con_MARKET_CAP = 200 # 流通市值标准
    
    # 初始化综合风险结果
    g.ris = 10
    g.ar = 1
    
    # 记录真实RSI_F和AR
    g.RIS_T = 0
    g.AR_T = 0
    
    # 上次风险判断标准
    g.risk_flag = 1
    g.buy_flag = 0
    
    # 初始化风险变化趋势数据
    g.risk_day1 = 0
    g.risk_day2 = 0
    g.risk_day3 = 0
    g.risk_list = [50]
    
    # 初始化风险参数
    g.con_FAST_RSI = 20
    g.con_SLOW_RSI = 60
    g.con_AR_COUNT = 26 # 以4天为期间计算AR值（普通为26天），反应长期趋势
    
    # 初始化当日买卖列表
    g.stock_buy = []
    g.stock_sell = []
    
    g.df_result = pd.DataFrame()
    
    run_weekly(weekly23, 1, time='open')
    run_weekly(weekly23, 2, time='open')
    run_weekly(weekly23, 3, time='open')
    run_weekly(clean, 4, time='open')
    run_weekly(weekly23, 5, time='open')
    
    #run_daily(daily, time='open')

# 取得对应股票代码的RSI风险指标
def get_RSI(stock):
     # 取得历史收盘价格
    df_hData = attribute_history(stock, 80, unit = '1d', fields = ('close', 'high', 'low'), skip_paused = True)
    df_hData_today = get_price(stock,start_date = g.d_today, end_date = g.d_today, frequency = 'daily', fields = ['close', 'high', 'low'])

    df_hData = df_hData.append(df_hData_today)
    
    closep = df_hData['close'].values
    
    RSI_F = tl.RSI(closep, timeperiod = g.con_FAST_RSI)
    RSI_S = tl.RSI(closep, timeperiod = g.con_SLOW_RSI)
    isFgtS = RSI_F > RSI_S
    
    rsiS = RSI_S[-1]
    rsiF = RSI_F[-1]
    
    '''
    慢速RSI 在55以上时，单边上涨市场，快速RSI上穿慢速RSI即可建仓
    慢速RSI 在55以下时，调整震荡市场，谨慎入市，取连续N天快速RSI大于慢速RSI建仓
    慢速RSI 在60以上时，牛市，无需减仓操作持仓即可
    '''
    # 基准仓位值
    bsFlag = 10
    
    if rsiS > 55 and isFgtS[-1]:
        bsFlag = 50 # "上行"
    elif rsiS > 68:
        bsFlag = 40 # "高位"
    elif rsiS > 60:
        bsFlag = 30 # "持仓"
    elif rsiS <= 55 \
        and isFgtS[-1] and isFgtS[-2] \
        and isFgtS[-3] and isFgtS[-4] \
        and isFgtS[-5] :
            bsFlag = 20 # "盘整建仓"
    else:
        bsFlag = 10 # "下行"
    
    g.RSI_T = rsiS
    
    return bsFlag
    
# 取得对应股票代码的AR活跃度指标
def get_AR(stock, count):
    df_ar = attribute_history(stock, count - 1, '1d', fields=('open', 'high', 'low'), skip_paused = True)
    df_ar_today = get_price(stock,start_date = g.d_today, end_date = g.d_today, frequency = 'daily', fields = ['open', 'high', 'low'])

    df_ar = df_ar.append(df_ar_today)
    
    ar = sum(df_ar['high'] - df_ar['open']) / sum(df_ar['open'] - df_ar['low']) * 100
    
    '''
    AR指标 在180以上时，股市极高活跃 
    AR指标 在120 - 180时，股市高活跃
    AR指标 在70 - 120时，股市盘整
    AR指标 在60 - 70以上时，股市走低
    AR指标 在60以下时，股市极弱
    '''
    brFlag = 1
    
    if ar > 180 :
        brFlag = 5
    elif ar > 120 and ar <= 180 :
        brFlag = 4
    elif ar > 70 and ar <= 120 :
        brFlag = 3
    elif ar > 60 and ar <= 70 :
        brFlag = 2
    else :
        brFlag = 1

    g.AR_T = ar
    
    return brFlag

# 取得对应大盘的风险
def get_stock_risk(stock, count):
    # 今日风险估算
    rsi = get_RSI(stock)
    ar = get_AR(stock, count)
    
    g.ris = rsi
    g.ar = ar
    
    #record(AR_T=g.AR_T)
    
    g.risk_day1 = g.risk_day2
    g.risk_day2 = g.risk_day3
    g.risk_day3 = g.AR_T
    
    buy_flag = 2
    
    if rsi == 10:
        buy_flag = 0
    elif rsi == 20:
        buy_flag = 2
    else:
        buy_flag = 1

    # 趋势控制
    if g.risk_day1 < 60 and g.risk_day2 < 60 and g.risk_day3 < 60:
        # 持续低迷
        buy_flag = 0
    elif g.risk_day2 * 0.3 > g.risk_day3:
        # 急跌
        buy_flag = 0
    elif g.risk_day1 < g.risk_day2 and g.risk_day2 < g.risk_day3 and \
        g.risk_day3 < 80 and g.risk_day3 > 65:
        # 弱市回升
        buy_flag = 1
    elif g.risk_day1 > g.risk_day2 and g.risk_day2 > g.risk_day3 and \
        g.risk_day3 < 150 and g.risk_day1 > 200:
        # 强市下跌
        buy_flag = 0
    elif g.risk_day1 > g.risk_day2 and g.risk_day2 > g.risk_day3 and \
        g.risk_day3 < 150 and g.risk_day1 > 150:
        # 中市下跌
        buy_flag = 2
    elif g.risk_day1 > g.risk_day2 * 0.95 and g.risk_day2 > g.risk_day3 and \
        g.risk_day3 < g.risk_day2 * 0.6 and g.risk_day1 > 180:
        # 强市下跌
        buy_flag = 0
    elif g.risk_day1 > 70 and g.risk_day2 > 70 and g.risk_day3 > 70:
        # 维持正常
        buy_flag = 1
    
    else:
        buy_flag = 2

    return buy_flag

def clean(context):
   
    for stock in context.portfolio.positions.keys():
        order_target(stock, 0)
    #weekly(context)
    log.info("定期清空")

# 开盘后止损止盈
def check_price(context, stock):
    price = context.portfolio.positions[stock].price
    avg_cost = context.portfolio.positions[stock].avg_cost
    
    if avg_cost  > price:
        return False
    else:
        return True
        
def weekly23(context):
    #if context.current_dt.isoweekday() <> 14:
    if len(context.portfolio.positions.keys()) <= 0:
       weekly(context)
       
def weekly(context):
    for stock in context.portfolio.positions.keys():
        order_target(stock, 0)

    cash = context.portfolio.cash
    log.info(g.stock_buy)
    for stock in g.stock_buy:
        order_value(stock, cash / len(g.stock_buy))
    
    if len(g.df_result.index) > 0:
        log.info(g.df_result)

def daily(context):
    for stock in g.stock_sell:
        order_target(stock, 0)
    
    cash = context.portfolio.cash
    
    for stock in g.stock_buy:
        order_value(stock, cash / len(g.stock_buy))
        
# 获得每天的数据
def get_stock_list(context):
    # 取得流通市值200亿以下的股票数据
    d_startdate = (context.current_dt  - timedelta(days = g.con_START_DATE)).strftime("%Y-%m-%d")
    
    q = query(
		valuation.code, valuation.circulating_cap
	).filter(
	    valuation.code.notin_(['002473.XSHE', '000407.XSHE']),
	    valuation.circulating_market_cap < g.con_MARKET_CAP
    )
    
    df = get_fundamentals(q, date = d_startdate)

    df.index = list(df['code'])

    # 去除ST，*ST
    st = get_extras('is_st', list(df['code']), start_date = g.d_today, end_date = g.d_today, df = True)
    st = st.iloc[0]
    stock_list = list(st[st == False].index)
    
    days = 29
    
    # 获得股票池数据
    df_list = get_price(stock_list, start_date=g.d_today, end_date=g.d_today, frequency='daily', fields=['open', 'close', 'high', 'low', 'paused', 'volume'])

    # 获取收盘价
    df_close = history(days, unit='1d', field='close', security_list = stock_list, skip_paused=True)
    df_close = df_close.append(df_list['close'])
    
    # 获取收盘价
    df_high = history(days, unit='1d', field='high', security_list = stock_list, skip_paused=True)
    df_high = df_high.append(df_list['high'])
    
    # 获取收盘价
    df_low = history(days, unit='1d', field='low', security_list = stock_list, skip_paused=True)
    df_low = df_low.append(df_list['low'])
    
    # 获取历史停牌
    df_paused_sum = history(days, unit='1d', field='paused', security_list = stock_list)
    df_paused_sum = df_paused_sum.append(df_list['paused'])
    df_paused_sum = pd.DataFrame(np.sum(df_paused_sum))
    df_paused_sum.columns = ['paused_sum']
    
    # 获取成交量
    df_volume = df_list['volume']
    df_volume = df_volume.T 
    
    for col in df_volume.columns:
        df_volume[col] = df_volume[col] / (df['circulating_cap'] * 100)
        
    df_volume.columns = ['volume']
    
    # 最高价的最高价
    df_high_h = pd.DataFrame(df_high.max())
    df_high_h.columns = ['high_h']
    
    # 最低价的最低价
    df_low_l = pd.DataFrame(df_low.min())
    df_low_l.columns = ['low_l']
    
    # 收盘价的最高价
    df_close_h = pd.DataFrame(df_high.max())
    df_close_h.columns = ['close_h']
    
    # 收盘价的最低价
    df_close_l = pd.DataFrame(df_close.min())
    df_close_l.columns = ['close_l']
    
    # 前15日最高价
    df_15_h = pd.DataFrame(df_high.head(15).max())
    df_15_h.columns = ['15_h']
    
    # 后15日最低价
    df_15_l = pd.DataFrame(df_low.tail(15).min())
    df_15_l.columns = ['15_l']
    
    # 开始日收盘价
    df_start = df_close.head(1)
    df_start.index = ['start']
    df_start = df_start.T
    
    # 结束日收盘价
    df_end = df_close.tail(1)
    df_end.index = ['end']
    df_end = df_end.T
    
    # 获取停牌
    df_paused = df_list['paused'].T
    df_paused.columns = ['paused']
    
    df_result = pd.concat([df_start, df_end], axis = 1, join_axes = [df_start.index])
    df_result = pd.concat([df_result, df_paused], axis = 1, join_axes = [df_result.index])
    df_result = pd.concat([df_result, df_volume], axis = 1, join_axes = [df_result.index])
    df_result = pd.concat([df_result, df_high_h], axis = 1, join_axes = [df_result.index])
    df_result = pd.concat([df_result, df_low_l], axis = 1, join_axes = [df_result.index])
    df_result = pd.concat([df_result, df_close_h], axis = 1, join_axes = [df_result.index])
    df_result = pd.concat([df_result, df_close_l], axis = 1, join_axes = [df_result.index])
    df_result = pd.concat([df_result, df_15_h], axis = 1, join_axes = [df_result.index])
    df_result = pd.concat([df_result, df_15_l], axis = 1, join_axes = [df_result.index])
    
    df_result = df_result[df_result['paused'] == 0]

    df_result['usual_wave'] = (df_result['close_h'] - df_result['close_l']) / df_result['start']
    df_result['max_wave'] = (df_result['high_h'] - df_result['low_l']) / df_result['start']
    df_result['start_end'] = (df_result['end'] - df_result['start']) / df_result['start']
   
    
    df_result['usual_wave'] = df_result['usual_wave'] / df_result['max_wave']
    df_result['start_end'] = df_result['start_end'] / df_result['usual_wave']
    #df_result = df_result[df_result['usual_wave'] < 1]
    
    df_result = df_result[df_result['start_end'] < 0]
    df_result = df_result[df_result['15_h'] == df_result['high_h']]
    df_result = df_result[df_result['15_l'] == df_result['low_l']]
    
    df_result = df_result.sort(columns = 'usual_wave', ascending = False).head(5)
    df_result = df_result.sort(columns = 'start_end', ascending = False).tail(1)
    
    df_result = df_result[df_result['start_end'] / df_result['max_wave'] > -0.85]
    df_result = df_result[df_result['max_wave'] < 0.7]

    g.df_result = df_result
    g.stock_buy = set(list(g.stock_buy) + list(df_result.index))
    
# 每天交易前调用
def before_trading_start(context):
    # 昨天
    g.d_yesterday = (context.current_dt  - timedelta(days = 1)).strftime("%Y-%m-%d")
    
    # 今天
    g.d_today = (context.current_dt).strftime("%Y-%m-%d")
    
# 每个单位时间(如果按天回测,则每天调用一次,如果按分钟,则每分钟调用一次)调用一次
def handle_data(context, data):
    pass

# 每天交易后调用
def after_trading_end(context):
    g.buy_flag = get_stock_risk(g.riskbench, 4)
    g.stock_buy = []
    g.stock_sell = []

    if g.buy_flag <> 0:
        get_stock_list(context)
    
        
    