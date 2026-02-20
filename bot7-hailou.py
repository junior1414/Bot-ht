import websocket
import json
import time
import requests
import sys

# --- CONFIGURAÇÃO ---
TOKEN = "8425840568:AAEkWXmLKKIpD7gH4X-3miGPpKoIk8N8au4"
CHAT_ID = "6830551391"
WS_URL = "wss://swarm.7games.bet.br/"
SITE_ID = 18751367

odds_abertura = {} 
conexao_perdida = False 

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mensagem, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        print("⚠️ Erro Telegram", flush=True)

def extrair(obj, *keys):
    temp = obj
    for k in keys:
        if isinstance(temp, dict) and k in temp: temp = temp[k]
        else: return 0
    return int(temp) if temp is not None else 0

def obter_odds_dinamicas(game_obj, placar_total):
    odds = {"1": 0.0, "2": 0.0, "prox_over": "0.00", "linha": placar_total + 0.5}
    try:
        markets = game_obj.get('market', {})
        for m_id, m_obj in markets.items():
            if m_obj.get('display_key') in ["WINNER", "P1XP2"]:
                events = m_obj.get('event', {})
                for e_id, e_obj in events.items():
                    if e_obj.get('type_1') == "W1": odds["1"] = float(e_obj.get('price', 0))
                    if e_obj.get('type_1') == "W2": odds["2"] = float(e_obj.get('price', 0))
            if m_obj.get('type') == "OverUnder":
                events = m_obj.get('event', {})
                for e_id, e_obj in events.items():
                    if e_obj.get('type_1') == "Over" and e_obj.get('base') == odds["linha"]:
                        odds["prox_over"] = f"{e_obj.get('price', 0):.2f}"
    except: pass
    return odds

def verificar_filtros_e_alertar(g_id, jogo):
    try:
        tempo = int(jogo['tempo'])
        gols = jogo['placar'].split('-')
        g1, g2 = int(gols[0]), int(gols[1])
        s = jogo['stats']
        
        if tempo <= 1:
            odds_abertura[g_id] = {"1": jogo['odds']['1'], "2": jogo['odds']['2'], "alertado": False}
            return

        if g_id not in odds_abertura:
            if g1 == g2: odds_abertura[g_id] = {"1": jogo['odds']['1'], "2": jogo['odds']['2'], "alertado": False}
            else: return 

        if not (14 <= tempo <= 26): return
        if odds_abertura[g_id].get('alertado'): return
        
        o_ref = odds_abertura[g_id]
        is_t1_fav = 1.0 < o_ref['1'] <= 2.0
        is_t2_fav = 1.0 < o_ref['2'] <= 2.0
        
        alerta = False
        if is_t1_fav and (g1 <= g2):
            alerta, t_fav, ap_f, ch_a, ch_f = True, jogo['time1'], s['atq_p'][0], s['ch_alvo'][0], s['ch_fora'][0]
        elif is_t2_fav and (g2 <= g1):
            alerta, t_fav, ap_f, ch_a, ch_f = True, jogo['time2'], s['atq_p'][1], s['ch_alvo'][1], s['ch_fora'][1]

        if alerta and (ch_a + ch_f >= 4) and ch_a >= 2:
            ap_min = ap_f / tempo
            msg = (
                f"🎯 *ALERTA: GOL HT (OVER 0.5)*\n"
                f"🔥 *PRESSÃO DO FAVORITO DETECTADA*\n\n"
                f"🏆 {jogo['liga']}\n"
                f"⚽ {jogo['time1']} *{jogo['placar']}* {jogo['time2']}\n"
                f"⏱ Tempo: {tempo}' min\n\n"
                f"⭐ *Favorito:* {t_fav}\n"
                f"📊 *AP/Min:* {ap_min:.2f}\n"
                f"📈 *Odd Over {jogo['odds']['linha']}:* {jogo['odds']['prox_over']}\n\n"
                f"📝 *STATS:* {s['atq_p'][0]}-{s['atq_p'][1]} AP | {s['ch_alvo'][0]}-{s['ch_alvo'][1]} Alvo"
            )
            enviar_telegram(msg)
            odds_abertura[g_id]['alertado'] = True
    except: pass

def executar():
    global conexao_perdida
    ws = None
    try:
        # HEADERS ESSENCIAIS PARA O RAILWAY NÃO SER BLOQUEADO
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Origin": "https://7games.bet.br",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache"
        }
        
        ws = websocket.create_connection(WS_URL, timeout=20, header=headers)
        
        if conexao_perdida:
            print("✅ Conexão restabelecida!", flush=True)
            conexao_perdida = False

        ws.send(json.dumps({"command": "request_session", "params": {"site_id": SITE_ID, "language": "pt"}, "rid": 1}))
        ws.recv() 
        ws.send(json.dumps({
            "command": "get",
            "params": {
                "source": "betting", "what": {
                    "sport": ["name"], "competition": ["name"], 
                    "game": ["id", "team1_name", "team2_name", "info", "stats"],
                    "market": ["type", "display_key"], "event": ["type_1", "price", "base"]
                },
                "where": {"game": {"type": 1}, "sport": {"id": 1}}, "subscribe": False
            }, "rid": 2
        }))
        
        res = json.loads(ws.recv())
        data_root = res.get('data', {}).get('data', {})
        sports = data_root.get('sport', {})
        
        if '1' in sports:
            print(f"📡 Monitorando {time.strftime('%H:%M:%S')}", flush=True)
            for c_id, c_obj in sports['1'].get('competition', {}).items():
                for g_id, g_obj in c_obj.get('game', {}).items():
                    info, st = g_obj.get('info', {}), g_obj.get('stats', {})
                    g1, g2 = int(info.get('score1', 0)), int(info.get('score2', 0))
                    t = int(info.get('current_game_time', 0))
                    
                    jogo_data = {
                        "liga": c_obj.get('name', ''), "time1": g_obj.get('team1_name'), "time2": g_obj.get('team2_name'),
                        "placar": f"{g1}-{g2}", "tempo": str(t),
                        "odds": obter_odds_dinamicas(g_obj, g1+g2),
                        "stats": {
                            "atq_p": [extrair(st, 'dangerous_attack', 'team1_value'), extrair(st, 'dangerous_attack', 'team2_value')],
                            "ch_alvo": [extrair(st, 'shot_on_target', 'team1_value'), extrair(st, 'shot_on_target', 'team2_value')],
                            "ch_fora": [extrair(st, 'shot_off_target', 'team1_value'), extrair(st, 'shot_off_target', 'team2_value')],
                        }
                    }
                    verificar_filtros_e_alertar(g_id, jogo_data)
        else:
            print("⏳ Sem jogos ao vivo agora.", flush=True)

    except Exception as e:
        if not conexao_perdida:
            print(f"⚠️ Conexão falhou: {e}", flush=True)
            conexao_perdida = True
        time.sleep(15)
    finally:
        if ws: 
            try: ws.close()
            except: pass

if __name__ == "__main__":
    print("🚀 BOT ATIVO NO RAILWAY", flush=True)
    while True:
        try: executar()
        except: pass
        time.sleep(25)