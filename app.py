import os, time, math, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify, render_template, request
app=Flask(__name__)
BASE='https://api.bitget.com'
S=requests.Session()
def api(path, params=None):
    r=S.get(BASE+path,params=params,timeout=12); r.raise_for_status(); j=r.json()
    if j.get('code')!='00000': raise ValueError(str(j.get('msg','API error')))
    return j.get('data',[])
def ema(a,n):
    v=a[0]; out=[]; k=2/(n+1)
    for x in a: v=x*k+v*(1-k); out.append(v)
    return out
def rsi(a,n=14):
    gains=[]; losses=[]
    for i in range(1,len(a)):
        d=a[i]-a[i-1]; gains.append(max(0,d)); losses.append(max(0,-d))
    g=sum(gains[:n])/n; l=sum(losses[:n])/n
    for i in range(n,len(gains)): g=(g*(n-1)+gains[i])/n; l=(l*(n-1)+losses[i])/n
    return 100 if l==0 else 100-100/(1+g/l)
def pivots(a,low=True,w=3):
    return [i for i in range(w,len(a)-w) if a[i]==(min if low else max)(a[i-w:i+w+1])]
def divergence(close,rsis):
    # Only confirmed pivots; momentum series aligned with close.
    for low in (True,False):
        ps=pivots(close,low)
        if len(ps)<2: continue
        i,j=ps[-2:]
        if j-i>40: continue
        if low and close[j]<close[i] and rsis[j]>rsis[i]+2: return 'bullish'
        if not low and close[j]>close[i] and rsis[j]<rsis[i]-2: return 'bearish'
    return 'none'
def candles(symbol,gran):
    data=api('/api/v2/mix/market/candles',{'symbol':symbol,'productType':'USDT-FUTURES','granularity':gran,'limit':'230'})
    rows=sorted(data,key=lambda x:int(x[0]))
    # Ignore current unfinished candle, using interval in milliseconds.
    minutes={'5m':5,'15m':15,'1H':60,'4H':240,'1D':1440}[gran]
    now=int(time.time()*1000)
    rows=[r for r in rows if int(r[0])+minutes*60000<=now]
    if len(rows)<205: raise ValueError('확정봉 데이터 부족')
    return rows
def analyze(symbol,gran):
    rows=candles(symbol,gran); c=[float(x[4]) for x in rows]; h=[float(x[2]) for x in rows]; l=[float(x[3]) for x in rows]; v=[float(x[5]) for x in rows]
    e20=ema(c,20);e50=ema(c,50);e200=ema(c,200)
    rs=[50.0]*15
    for k in range(16,len(c)+1): rs.append(rsi(c[:k]))
    rs=rs[:len(c)]
    mac=[a-b for a,b in zip(ema(c,12),ema(c,26))]; sig=ema(mac,9)
    vol=sum(v[-21:-1])/20; ratio=v[-1]/vol if vol else 0
    prev_hi=max(h[-21:-1]);prev_lo=min(l[-21:-1]); price=c[-1]
    bull=e20[-1]>e50[-1]>e200[-1] and mac[-1]>sig[-1] and 48<=rs[-1]<=72
    bear=e20[-1]<e50[-1]<e200[-1] and mac[-1]<sig[-1] and 28<=rs[-1]<=52
    div=divergence(c,rs)
    br_up=price>prev_hi and ratio>=1.2; br_down=price<prev_lo and ratio>=1.2
    # Wick-heavy breakout is considered a potential false breakout.
    rng=max(h[-1]-l[-1],1e-12); pos=(price-l[-1])/rng
    fake_up=br_up and pos<0.65; fake_down=br_down and pos>0.35
    direction='LONG' if bull else 'SHORT' if bear else 'WAIT'
    if direction=='LONG' and fake_up or direction=='SHORT' and fake_down: direction='WAIT'
    if direction=='LONG' and div=='bearish' or direction=='SHORT' and div=='bullish': direction='WAIT'
    # ATR 14, stop behind recent swing with ATR buffer.
    trs=[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])) for i in range(1,len(c))]
    atr=sum(trs[-14:])/14
    stop=(min(l[-11:-1])-0.2*atr) if direction=='LONG' else (max(h[-11:-1])+0.2*atr) if direction=='SHORT' else None
    risk=abs(price-stop) if stop is not None else 0
    target=(price+2*risk if direction=='LONG' else price-2*risk if direction=='SHORT' else None)
    if risk<=0 or (target is not None and target<=0): direction='WAIT';stop=None;target=None
    return {'symbol':symbol,'timeframe':gran,'price':price,'rsi':round(rs[-1],1),'volume_ratio':round(ratio,2),'divergence':div,'trend':'UP' if e20[-1]>e50[-1]>e200[-1] else 'DOWN' if e20[-1]<e50[-1]<e200[-1] else 'MIXED','breakout':'UP' if br_up else 'DOWN' if br_down else 'NONE','fake_breakout':fake_up or fake_down,'direction':direction,'stop':stop,'target':target,'support':prev_lo,'resistance':prev_hi,'last_closed':int(rows[-1][0]),'reason':'확정봉 EMA20/50/200, MACD, RSI, 거래량 및 돌파 검증'}
def symbols(min_turnover):
    data=api('/api/v2/mix/market/tickers',{'productType':'USDT-FUTURES'})
    out=[]
    for x in data:
        try:
            sym=x['symbol']; turn=float(x.get('usdtVolume',0))
            if sym.endswith('USDT') and turn>=min_turnover: out.append((sym,turn))
        except (ValueError,KeyError,TypeError): pass
    return sorted(out,key=lambda z:z[1],reverse=True)
def scan_one(sym,mode):
    frames=['5m','15m','1H'] if mode=='scalp' else ['1H','4H','1D']
    a,b,c=[analyze(sym,f) for f in frames]
    d=b['direction']; aligned=d!='WAIT' and c['trend']==('UP' if d=='LONG' else 'DOWN')
    div_ok=a['divergence'] in ('bullish','none') if d=='LONG' else a['divergence'] in ('bearish','none')
    valid=aligned and div_ok and not b['fake_breakout']
    # Recompute stop from setup candle, RR2 is a proposed scenario not a forecast.
    return {'symbol':sym,'mode':mode,'signal':d if valid else 'WAIT','setup':b,'higher':c['trend'],'trigger':a['divergence'],'status':'후보 · 진입 전 재확인' if valid else '관망','invalidation':b['stop'] if valid else None,'rr':2 if valid else None}
# Watchlist symbols are evaluated regardless of signal strength or turnover filter.
MAJORS = ['BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT','BNBUSDT','DOGEUSDT','ADAUSDT','LINKUSDT','AVAXUSDT','SUIUSDT']
@app.route('/api/majors')
def majors():
    mode=request.args.get('mode','scalp')
    if mode not in ('scalp','swing'): return jsonify(error='잘못된 분석 모드'),400
    try:
        available={s for s,_ in symbols(0)}
    except Exception as e:
        return jsonify(error='Bitget 종목 목록 조회 실패: '+str(e)),502
    results=[]; errors=[]
    selected=[s for s in MAJORS if s in available]
    for s in MAJORS:
        if s not in available: errors.append({'symbol':s,'error':'현재 USDT 선물 종목 목록에 없음'})
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(scan_one,s,mode):s for s in selected}
        for fut in as_completed(futures):
            try: results.append(fut.result())
            except Exception as e: errors.append({'symbol':futures[fut],'error':str(e)[:120]})
    results.sort(key=lambda x:MAJORS.index(x['symbol']))
    return jsonify(results=results,errors=errors,server_time=int(time.time()))
@app.route('/')
def home(): return render_template('index.html')
@app.route('/api/scan')
def scan():
    mode=request.args.get('mode','scalp'); mode=mode if mode in ('scalp','swing') else 'scalp'
    try: minimum=max(0,float(request.args.get('min_turnover',1000000)))
    except ValueError: return jsonify(error='거래대금 설정 오류'),400
    try: syms=symbols(minimum)
    except Exception as e: return jsonify(error='Bitget 종목 조회 실패: '+str(e)),502
    # Limit work per request to protect free hosting; all eligible symbols scanned in batches by client.
    try: offset=max(0,int(request.args.get('offset',0)))
    except ValueError: offset=0
    batch=syms[offset:offset+8]; results=[]; errors=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(scan_one,s,mode):s for s,_ in batch}
        for fut in as_completed(futures):
            try: results.append(fut.result())
            except Exception as e: errors.append({'symbol':futures[fut],'error':str(e)[:120]})
    return jsonify(total=len(syms),offset=offset,next_offset=offset+len(batch),results=results,errors=errors,server_time=int(time.time()))
if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))
