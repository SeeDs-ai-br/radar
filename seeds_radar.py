# -*- coding: utf-8 -*-
"""
SeeDs Radar — curadoria estratégica de notícias
================================================
Visita feeds das principais fontes do mundo (IA, empresas de IA, vendas,
empreendedorismo, tecnologia, economia, mundo, política, energia e negócios),
LÊ a matéria completa localmente, extrai a essência (útil quando há paywall),
gera a leitura estratégica em três atos (a matéria diz → por trás disso →
conexão nesta edição) e renderiza um HTML único no padrão visual SeeDS.

Uso:
    python seeds_radar.py            -> gera a edição PESSOAL (index.html, com essência completa)
    python seeds_radar.py --publico  -> gera a edição PÚBLICA em docs/ (sem parágrafos copiados —
                                        troca por citação curta com crédito; segura para publicar)
    python seeds_radar.py --loop     -> gera e repete a cada 5 horas (deixe rodando)
    python seeds_radar.py --ai       -> enriquece os insights com a API da Anthropic
                                        (requer ANTHROPIC_API_KEY e `pip install anthropic`)

A tarefa agendada do Windows ("SeeDs Radar") roda este script a cada 5 horas.
A pasta docs/ é o que fica público no GitHub Pages — o restante nunca é publicado.
"""

import base64
import hashlib
import html as htmllib
import io
import json
import re
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent
MIDIA = Path(r"C:\Users\f8069391\OneDrive - TIM\Área de Trabalho\Seeds\Mídia")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
INTERVALO_HORAS = 5
CTA_ASSINE_URL = ""  # link de assinatura (Canal do WhatsApp, formulário etc.) — preencher quando existir

# ---------------------------------------------------------------- categorias

CATEGORIAS = [
    ("ia", "Inteligência Artificial"),
    ("ia_negocios", "Empresas de IA"),
    ("vendas", "Vendas & Growth"),
    ("empreendedorismo", "Empreendedorismo"),
    ("tecnologia", "Tecnologia"),
    ("economia", "Economia"),
    ("mundo", "Mundo"),
    ("politica", "Política"),
    ("energia", "Energia & Clima"),
    ("negocios", "Negócios & Estratégia"),
]

GN_PT = "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
GN_EN = "&hl=en-US&gl=US&ceid=US:en"

FEEDS = [
    # IA (pesquisa, modelos, sociedade)
    {"cat": "ia", "fonte": "MIT Technology Review", "lang": "en", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed"},
    {"cat": "ia", "fonte": "TechCrunch AI", "lang": "en", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"cat": "ia", "fonte": "The Verge AI", "lang": "en", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"cat": "ia", "fonte": "Google News BR", "lang": "pt", "url": "https://news.google.com/rss/search?q=%22intelig%C3%AAncia%20artificial%22" + GN_PT},
    # Empresas de IA (negócio, captações, lançamentos, receita)
    {"cat": "ia_negocios", "fonte": "VentureBeat AI", "lang": "en", "url": "https://venturebeat.com/category/ai/feed/"},
    {"cat": "ia_negocios", "fonte": "The Decoder", "lang": "en", "url": "https://the-decoder.com/feed/"},
    {"cat": "ia_negocios", "fonte": "Google News", "lang": "en", "url": "https://news.google.com/rss/search?q=%28OpenAI%20OR%20Anthropic%20OR%20%22AI%20startup%22%29%20%28funding%20OR%20raises%20OR%20revenue%20OR%20launches%29" + GN_EN},
    {"cat": "ia_negocios", "fonte": "Google News BR", "lang": "pt", "url": "https://news.google.com/rss/search?q=%22startup%20de%20IA%22%20OR%20%22empresa%20de%20intelig%C3%AAncia%20artificial%22" + GN_PT},
    # Vendas & Growth (o que alavancou vendas no mundo dos negócios)
    {"cat": "vendas", "fonte": "HubSpot Sales", "lang": "en", "url": "https://blog.hubspot.com/sales/rss.xml"},
    {"cat": "vendas", "fonte": "Salesforce Blog", "lang": "en", "url": "https://www.salesforce.com/blog/feed/"},
    {"cat": "vendas", "fonte": "Google News BR", "lang": "pt", "url": "https://news.google.com/rss/search?q=%22recorde%20de%20vendas%22%20OR%20%22crescimento%20de%20vendas%22%20OR%20%22vendas%20crescem%22" + GN_PT},
    {"cat": "vendas", "fonte": "Google News", "lang": "en", "url": "https://news.google.com/rss/search?q=%22sales%20growth%22%20OR%20%22record%20sales%22%20OR%20%22revenue%20growth%22" + GN_EN},
    # Empreendedorismo
    {"cat": "empreendedorismo", "fonte": "TechCrunch Startups", "lang": "en", "url": "https://techcrunch.com/category/startups/feed/"},
    {"cat": "empreendedorismo", "fonte": "Crunchbase News", "lang": "en", "url": "https://news.crunchbase.com/feed/"},
    {"cat": "empreendedorismo", "fonte": "Entrepreneur", "lang": "en", "url": "https://www.entrepreneur.com/latest.rss"},
    {"cat": "empreendedorismo", "fonte": "Startups.com.br", "lang": "pt", "url": "https://startups.com.br/feed/"},
    {"cat": "empreendedorismo", "fonte": "Google News BR", "lang": "pt", "url": "https://news.google.com/rss/search?q=empreendedorismo%20OR%20%22novo%20neg%C3%B3cio%22%20OR%20unic%C3%B3rnio" + GN_PT},
    # Tecnologia
    {"cat": "tecnologia", "fonte": "The Verge", "lang": "en", "url": "https://www.theverge.com/rss/index.xml"},
    {"cat": "tecnologia", "fonte": "Ars Technica", "lang": "en", "url": "https://feeds.arstechnica.com/arstechnica/index"},
    {"cat": "tecnologia", "fonte": "Wired", "lang": "en", "url": "https://www.wired.com/feed/rss"},
    {"cat": "tecnologia", "fonte": "Canaltech", "lang": "pt", "url": "https://canaltech.com.br/rss/"},
    # Economia
    {"cat": "economia", "fonte": "BBC Business", "lang": "en", "url": "https://feeds.bbci.co.uk/news/business/rss.xml"},
    {"cat": "economia", "fonte": "CNBC Economy", "lang": "en", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"},
    {"cat": "economia", "fonte": "InfoMoney", "lang": "pt", "url": "https://www.infomoney.com.br/feed/"},
    {"cat": "economia", "fonte": "G1 Economia", "lang": "pt", "url": "https://g1.globo.com/rss/g1/economia/"},
    # Mundo
    {"cat": "mundo", "fonte": "BBC World", "lang": "en", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"cat": "mundo", "fonte": "Al Jazeera", "lang": "en", "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"cat": "mundo", "fonte": "The Guardian", "lang": "en", "url": "https://www.theguardian.com/world/rss"},
    {"cat": "mundo", "fonte": "G1 Mundo", "lang": "pt", "url": "https://g1.globo.com/rss/g1/mundo/"},
    # Política
    {"cat": "politica", "fonte": "G1 Política", "lang": "pt", "url": "https://g1.globo.com/rss/g1/politica/"},
    {"cat": "politica", "fonte": "BBC Brasil", "lang": "pt", "url": "https://feeds.bbci.co.uk/portuguese/rss.xml"},
    {"cat": "politica", "fonte": "Politico", "lang": "en", "url": "https://rss.politico.com/politics-news.xml"},
    # Energia & Clima
    {"cat": "energia", "fonte": "Guardian Environment", "lang": "en", "url": "https://www.theguardian.com/environment/rss"},
    {"cat": "energia", "fonte": "OilPrice", "lang": "en", "url": "https://oilprice.com/rss/main"},
    # Negócios & Estratégia
    {"cat": "negocios", "fonte": "Harvard Business Review", "lang": "en", "url": "http://feeds.hbr.org/harvardbusiness"},
    {"cat": "negocios", "fonte": "Fast Company", "lang": "en", "url": "https://www.fastcompany.com/latest/rss"},
    {"cat": "negocios", "fonte": "Exame", "lang": "pt", "url": "https://exame.com/feed/"},
]

# ------------------------------------------------------ motor de correlações

TEMAS = {
    "ia_generativa": {
        "label": "IA generativa",
        "kw": ["openai", "anthropic", "chatgpt", "claude", "gemini", " llm", "modelo de linguagem",
               "generative ai", "genai", "ia generativa", "artificial intelligence",
               "inteligência artificial", "copilot", "mistral", "deepseek", "llama", "agente de ia", "ai agent", "ai model"],
        "insights": [
            "Por trás do anúncio, o que muda é o custo de produzir trabalho intelectual — inclusive proposta, atendimento e prospecção. Quem redesenha o funil com IA compra vantagem de margem antes do concorrente; o resto paga para alcançar depois.",
            "Cada salto de modelo reprecifica o que é 'trabalho humano premium'. O movimento a observar: quais etapas da operação comercial ficam automatizáveis em 12 meses — e como ocupar o espaço consultivo que sobra, que é onde o valor migra.",
        ],
        "correl": [
            {"tema": "Semicondutores & data centers", "efeito": "Modelos maiores puxam GPUs, energia e capex de nuvem — Nvidia e TSMC antecipam o ritmo do setor em meses.", "onde": [("SemiAnalysis", "https://semianalysis.com"), ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/")]},
            {"tema": "Mercado de trabalho", "efeito": "Funções comerciais e de atendimento são redesenhadas antes das demais — vagas e demissões em tech contam essa história primeiro.", "onde": [("LinkedIn Economic Graph", "https://economicgraph.linkedin.com"), ("Layoffs.fyi", "https://layoffs.fyi")]},
            {"tema": "Regulação de IA", "efeito": "AI Act na Europa e PL 2338 no Brasil definem o custo de compliance de quem vende IA.", "onde": [("MIT Tech Review", "https://www.technologyreview.com"), ("Senado · PL 2338", "https://www25.senado.leg.br/web/atividade/materias/-/materia/157233")]},
        ],
    },
    "negocio_ia": {
        "label": "Negócio de IA",
        "kw": ["funding", "captação", "captou", "raises", "raised", "valuation", "aporte", "rodada",
               "series a", "series b", "série a", "série b", "ai startup", "startup de ia", "openai", "anthropic"],
        "insights": [
            "Siga o dinheiro, não o demo: onde o capital entra em IA hoje é onde o mercado corporativo vai comprar em dois anos. Cada captação dessas revela uma dor que alguém validou com cheque — e um mapa de futuros concorrentes ou parceiros da SeeDs.",
            "Por trás da rodada há uma tese de receita: qual cliente paga, por qual dor, com que ticket. Decodificar isso vale mais que o valuation da manchete — é benchmarking de modelo de negócio de graça.",
        ],
        "correl": [
            {"tema": "Juros & liquidez", "efeito": "O funding de risco é a ponta mais sensível do ciclo de juros — quando o custo de capital cai, as rodadas voltam primeiro em IA.", "onde": [("Crunchbase News", "https://news.crunchbase.com"), ("FRED", "https://fred.stlouisfed.org")]},
            {"tema": "Adoção corporativa", "efeito": "Captação forte vira pressão de venda: essas empresas vão bater na porta dos mesmos clientes que você atende.", "onde": [("The Decoder", "https://the-decoder.com"), ("CB Insights", "https://www.cbinsights.com/research/")]},
        ],
    },
    "vendas_growth": {
        "label": "Vendas & growth",
        "kw": ["vendas", "sales", "receita", "revenue", "faturamento", "growth", "crescimento de",
               "varejo", "e-commerce", "consumidor", " crm", "pipeline", "funil de", "conversão", "black friday"],
        "insights": [
            "Crescimento de vendas raramente é sorte: por trás há uma alavanca — canal, preço, proposta ou tecnologia. Identifique qual delas moveu esse resultado e pergunte o que a mesma alavanca faria no seu contexto.",
            "Quando um player anuncia recorde de vendas, o mercado inteiro herda o benchmark. Seus clientes vão se perguntar 'por que nós não?' — chegue antes com a resposta e o método.",
        ],
        "correl": [
            {"tema": "Tecnologia comercial", "efeito": "Os ganhos de conversão atuais vêm de dado + IA no funil, não de mais gente no time.", "onde": [("HubSpot Sales", "https://blog.hubspot.com/sales"), ("Salesforce Blog", "https://www.salesforce.com/blog/")]},
            {"tema": "Consumo & juros", "efeito": "Resultado de vendas forte sustenta a tese de consumo resiliente — e recalibra a régua de metas do próximo ciclo.", "onde": [("InfoMoney", "https://www.infomoney.com.br"), ("CNC", "https://portaldocomercio.org.br")]},
        ],
    },
    "startups": {
        "label": "Startups & empreendedorismo",
        "kw": ["startup", "venture", "unicórnio", "unicorn", "aceleradora", "empreendedor", "founder",
               "fundador", "pequenas empresas", " pme", "franquia", "bootstrapp", "novo negócio"],
        "insights": [
            "História de empreendedor é laboratório aberto: modelo de negócio, tração e erro alheio de graça. O exercício útil é extrair o padrão replicável — não a inspiração — e testar uma hipótese dessas na SeeDs ainda este mês.",
            "Por trás de cada caso de tração há uma escolha de nicho e de canal que ninguém conta na manchete. Leia procurando a decisão, não o resultado: é ela que se copia.",
        ],
        "correl": [
            {"tema": "Ciclo de funding", "efeito": "Funding aquecido significa concorrência subsidiada; ciclo seco significa consolidação e clientes órfãos de fornecedor — dois cenários, duas jogadas comerciais.", "onde": [("Crunchbase News", "https://news.crunchbase.com"), ("Distrito", "https://distrito.me")]},
        ],
    },
    "ma": {
        "label": "Fusões & aquisições",
        "kw": ["aquisição", "acquisition", "merger", "fusão", " adquire", "compra da", "compra a ", "buyout", "takeover"],
        "insights": [
            "M&A é o mercado apontando onde está o valor que o crescimento orgânico não alcança. Cada aquisição redesenha o mapa de fornecedores — e deixa clientes órfãos da marca comprada, que é exatamente onde abre janela comercial.",
        ],
        "correl": [
            {"tema": "Consolidação do setor", "efeito": "Onda de M&A comprime margens de quem fica de fora e encarece aquisição de clientes — antecipe de que lado você estará.", "onde": [("Crunchbase News", "https://news.crunchbase.com"), ("Exame Negócios", "https://exame.com/negocios/")]},
        ],
    },
    "chips": {
        "label": "Semicondutores",
        "kw": ["nvidia", "semicondutor", "semiconductor", " chip", "tsmc", "intel", " amd ", " gpu", "data center", "datacenter"],
        "insights": [
            "Semicondutor é o petróleo da economia digital: quem controla chip controla o ritmo da IA. O que acontece aqui chega ao mercado de software e serviços com seis meses de atraso — é vantagem de leitura para quem acompanha.",
            "Capex em chips e data centers é o indicador antecedente mais honesto do ciclo de IA. Investimento acelerando significa demanda por soluções digitais chegando — prepare o pipeline antes.",
        ],
        "correl": [
            {"tema": "Geopolítica Taiwan–EUA–China", "efeito": "Tensão no estreito de Taiwan mexe com toda a cadeia de eletrônicos e com o preço de hardware no Brasil.", "onde": [("Reuters Tech", "https://www.reuters.com/technology/"), ("CSIS", "https://www.csis.org")]},
            {"tema": "Energia", "efeito": "Data centers de IA disputam eletricidade com indústria e consumo — energia vira variável de custo de IA.", "onde": [("IEA", "https://www.iea.org"), ("OilPrice", "https://oilprice.com")]},
        ],
    },
    "juros_inflacao": {
        "label": "Juros & inflação",
        "kw": [" fed ", "federal reserve", "juros", "interest rate", "selic", "copom", "banco central",
               "inflação", "inflation", " cpi", " ipca", "treasury", "fiscal"],
        "insights": [
            "Juros são o preço do tempo — e mudam o apetite de risco de todo cliente B2B. Corte libera orçamento para inovação; alta trava decisão. O movimento certo é calibrar o timing e o argumento das propostas pelo ciclo, não contra ele.",
            "Por trás do número de inflação está o custo de esperar. Em aperto monetário, venda ROI de curto prazo; em afrouxamento, venda transformação. A notícia macro é insumo direto de discurso comercial.",
        ],
        "correl": [
            {"tema": "Câmbio", "efeito": "Diferencial de juros EUA–Brasil move o dólar, que move custo de nuvem e tecnologia importada.", "onde": [("BC · Focus", "https://www.bcb.gov.br/publicacoes/focus"), ("Investing BRL", "https://br.investing.com/currencies/usd-brl")]},
            {"tema": "Bolsa & crédito", "efeito": "Juros altos comprimem valuation de tech e encarecem capital de giro de PMEs — seus clientes sentem primeiro.", "onde": [("InfoMoney", "https://www.infomoney.com.br"), ("FRED", "https://fred.stlouisfed.org")]},
            {"tema": "Consumo", "efeito": "Crédito caro esfria varejo e serviços com defasagem de 2 a 3 trimestres.", "onde": [("IBGE", "https://www.ibge.gov.br"), ("CNC", "https://portaldocomercio.org.br")]},
        ],
    },
    "petroleo_energia": {
        "label": "Petróleo & energia",
        "kw": ["petróleo", " oil", "opep", "opec", "gás natural", "energia", "energy", "barril", "brent",
               "eletricidade", "renováve", "renewable", "solar", "eólica", "wind power", "nuclear"],
        "insights": [
            "Energia é a variável que conecta clima, geopolítica e inflação. Choque no barril chega ao frete, do frete ao preço, do preço ao juro — e do juro ao orçamento do seu cliente. É essa cadeia que vale mapear, não o preço do dia.",
            "A transição energética está reprecificando setores inteiros — e o boom de data centers é, no fundo, uma história de eletricidade. Quem lê o mapa de energia lê antes o mapa de investimento.",
        ],
        "correl": [
            {"tema": "Clima", "efeito": "Eventos climáticos extremos mexem com oferta de energia e commodities agrícolas ao mesmo tempo.", "onde": [("NOAA", "https://www.noaa.gov"), ("Guardian Environment", "https://www.theguardian.com/environment")]},
            {"tema": "Inflação & juros", "efeito": "Petróleo caro pressiona inflação global e adia cortes de juros.", "onde": [("OilPrice", "https://oilprice.com"), ("Trading Economics", "https://tradingeconomics.com")]},
            {"tema": "Data centers de IA", "efeito": "A conta de energia da IA já disputa capacidade de geração em vários países.", "onde": [("IEA", "https://www.iea.org/topics/data-centres-and-data-transmission-networks")]},
        ],
    },
    "cambio": {
        "label": "Câmbio",
        "kw": ["dólar", "dollar", "câmbio", "currency", "moeda", "euro "],
        "insights": [
            "Câmbio é o tradutor entre a notícia global e o caixa local. Dólar alto encarece nuvem, licença e hardware — e fortalece o argumento de soluções nacionais e de eficiência. Acompanhe como quem acompanha a própria tabela de custos.",
        ],
        "correl": [
            {"tema": "Juros EUA–Brasil", "efeito": "Diferencial de juros e percepção de risco fiscal são os motores do dólar-real.", "onde": [("BC · Focus", "https://www.bcb.gov.br/publicacoes/focus"), ("Investing BRL", "https://br.investing.com/currencies/usd-brl")]},
            {"tema": "Custo de TI", "efeito": "Nuvem, SaaS e hardware são dolarizados — o repasse chega em 1 a 2 trimestres.", "onde": [("InfoMoney", "https://www.infomoney.com.br/mercados/")]},
        ],
    },
    "geopolitica": {
        "label": "Geopolítica & comércio",
        "kw": ["china", "taiwan", "tarifa", "tariff", "sanções", "sanctions", "guerra comercial", "trade war",
               "geopolít", "exportaç", "importaç", "otan", "nato", "ucrânia", "ukraine", "oriente médio", "middle east"],
        "insights": [
            "Geopolítica virou variável de supply chain: tarifa, sanção e conflito redesenham rotas e custos — e criam janela para quem vende resiliência e eficiência. A pergunta é qual cadeia do seu cliente passa pelo ponto de tensão da manchete.",
            "Cada movimento EUA–China reprecifica tecnologia, chips e commodities. Ler o tabuleiro é ler o custo futuro da sua cadeia — e a agenda de risco que vai dominar a mesa do seu cliente no próximo trimestre.",
        ],
        "correl": [
            {"tema": "Commodities", "efeito": "Tensões em rotas de comércio mexem com frete, grãos, metais e petróleo simultaneamente.", "onde": [("Trading Economics", "https://tradingeconomics.com/commodities"), ("Al Jazeera", "https://www.aljazeera.com")]},
            {"tema": "Semicondutores", "efeito": "Restrições de exportação de chips definem quem consegue treinar IA de fronteira.", "onde": [("CSIS", "https://www.csis.org"), ("Reuters Tech", "https://www.reuters.com/technology/")]},
        ],
    },
    "trabalho": {
        "label": "Mercado de trabalho",
        "kw": ["emprego", "layoff", "demissã", "jobs report", "desemprego", "workforce", "contrataç", "payroll"],
        "insights": [
            "O mercado de trabalho é o termômetro social da IA e o termômetro macro do consumo. Demissão em tech sinaliza reorganização de custo — e abre a conversa de produtividade com quem ficou. Emprego fraco antecipa corte de orçamento nos seus clientes.",
        ],
        "correl": [
            {"tema": "Adoção de IA", "efeito": "Ondas de automação aparecem primeiro em vagas de atendimento, marketing e vendas.", "onde": [("Layoffs.fyi", "https://layoffs.fyi"), ("LinkedIn Economic Graph", "https://economicgraph.linkedin.com")]},
            {"tema": "Consumo & juros", "efeito": "Payroll forte nos EUA adia corte de juros — e mexe com câmbio e bolsa no Brasil.", "onde": [("FRED", "https://fred.stlouisfed.org")]},
        ],
    },
    "bigtech": {
        "label": "Big techs",
        "kw": ["google", "apple", "microsoft", "amazon", "alphabet", "zuckerberg", "facebook", "instagram", "big tech", "antitrust", "antitruste", "nuvem", "cloud"],
        "insights": [
            "Big techs definem a infraestrutura sobre a qual todo mundo vende — mudança de plataforma, preço ou política delas é mudança no seu campo de jogo. O que elas cortam ou dobram hoje vira tendência de orçamento corporativo em dois trimestres.",
        ],
        "correl": [
            {"tema": "Antitruste & regulação", "efeito": "Decisões nos EUA e na UE podem abrir (ou fechar) espaço para players menores.", "onde": [("The Verge", "https://www.theverge.com/tech"), ("Politico Tech", "https://www.politico.com/technology")]},
            {"tema": "Capex de IA", "efeito": "O investimento em data centers das big techs é o principal motor do ciclo atual de IA.", "onde": [("CNBC Tech", "https://www.cnbc.com/technology/")]},
        ],
    },
    "regulacao": {
        "label": "Regulação & privacidade",
        "kw": ["regulaç", "regulation", "ai act", "lei de ia", "marco legal", "compliance", "privacidade", "lgpd", "gdpr", "supremo", "stf"],
        "insights": [
            "Regulação é risco para quem improvisa e diferencial para quem se antecipa. Cada marco novo cria um mercado de adequação — a pergunta estratégica é qual dor de compliance dos seus clientes vira oferta da SeeDs.",
        ],
        "correl": [
            {"tema": "IA generativa", "efeito": "Regras de IA definem quais casos de uso escalam e quais travam — sobretudo em saúde e finanças.", "onde": [("ANPD", "https://www.gov.br/anpd/pt-br"), ("IAPP", "https://iapp.org")]},
        ],
    },
    "mercados": {
        "label": "Mercados",
        "kw": ["bolsa", "ibovespa", "wall street", "s&p", "nasdaq", "ações", "stocks", " ipo", "valuation", "earnings", "balanço", "resultado trimestral"],
        "insights": [
            "Bolsa é expectativa condensada: o preço de hoje é a aposta sobre o lucro de amanhã. Setor em alta indica onde haverá orçamento; setor em queda, onde haverá pressão por eficiência — são dois discursos de venda diferentes, escolha o certo.",
            "Temporada de balanços é inteligência competitiva gratuita: as calls de resultados dos seus clientes — e dos concorrentes deles — revelam prioridades de investimento antes de qualquer RFP.",
        ],
        "correl": [
            {"tema": "Juros", "efeito": "Valuation de tech é o ativo mais sensível à curva de juros.", "onde": [("Investing", "https://br.investing.com"), ("Status Invest", "https://statusinvest.com.br")]},
        ],
    },
    "cripto": {
        "label": "Cripto & ativos digitais",
        "kw": ["bitcoin", "crypto", "cripto", "ethereum", "stablecoin", " etf", "blockchain"],
        "insights": [
            "Cripto funciona como medidor de apetite de risco global: rali acompanha liquidez farta; queda brusca antecipa aversão a risco que respinga em orçamento de inovação. Leia como termômetro, não como tese.",
        ],
        "correl": [
            {"tema": "Juros & liquidez", "efeito": "O ciclo de liquidez do Fed é o principal vetor do preço de ativos de risco.", "onde": [("CoinDesk", "https://www.coindesk.com"), ("FRED", "https://fred.stlouisfed.org")]},
        ],
    },
    "telecom": {
        "label": "Telecom & conectividade",
        "kw": ["telecom", " 5g", "operadora", " tim ", "vivo", "claro", "anatel", "fibra", "conectividade", "starlink", "satélite"],
        "insights": [
            "Conectividade é a camada zero da economia digital — e o seu território. Movimentos em 5G, satélite e fibra redefinem onde nascem os próximos casos de uso de IA; leia como mapa de oportunidade interna na TIM e externa na SeeDs.",
        ],
        "correl": [
            {"tema": "IA & edge", "efeito": "Agentes de IA em tempo real dependem de latência — 5G e edge computing viram pré-requisito.", "onde": [("Teleco", "https://www.teleco.com.br"), ("Anatel", "https://www.gov.br/anatel/pt-br")]},
        ],
    },
    "clima": {
        "label": "Clima",
        "kw": ["clima", "climate", "cop3", "aquecimento", "enchente", "seca ", "el niño", "la niña", "desmatamento", "emissõ", "onda de calor", "heatwave"],
        "insights": [
            "Clima é variável econômica: seca mexe com energia e alimentos, enchente mexe com logística e seguros. O evento climático de hoje é a linha de custo do próximo trimestre — e bancos já precificam esse risco no crédito.",
        ],
        "correl": [
            {"tema": "Energia & alimentos", "efeito": "Hidrologia define preço de energia no Brasil; safra define inflação de alimentos.", "onde": [("ONS", "https://www.ons.org.br"), ("Conab", "https://www.conab.gov.br")]},
            {"tema": "Seguros & crédito", "efeito": "Eventos extremos reprecificam seguros e crédito rural em cascata.", "onde": [("Swiss Re Institute", "https://www.swissre.com/institute/")]},
        ],
    },
}

FALLBACK_INSIGHT = {
    "ia": "Movimento relevante no ecossistema de IA. A pergunta útil: isso muda o custo, a velocidade ou o risco de alguma decisão sua nos próximos 90 dias?",
    "ia_negocios": "Movimento de negócio no ecossistema de IA. Decodifique: isso cria fornecedor, concorrente ou benchmark para a SeeDs — e o que muda no seu pitch?",
    "vendas": "Resultado comercial que virou notícia carrega um método por trás. Identifique a alavanca — canal, preço, proposta ou tecnologia — e traga a lição para o seu funil.",
    "empreendedorismo": "História de empreendedor é laboratório aberto. Extraia o padrão replicável (nicho, canal, modelo), não a inspiração.",
    "tecnologia": "Tecnologia nova vira expectativa de cliente em ciclos cada vez mais curtos. O que essa novidade torna obsoleto no seu discurso atual?",
    "economia": "Sinal macro que altera o ambiente de decisão dos seus clientes. Ajuste timing e argumento ao ciclo — ROI curto em aperto, transformação em afrouxamento.",
    "mundo": "Evento global com efeito em cadeia potencial: câmbio, commodities, supply chain. Qual das três pontas toca o seu negócio primeiro?",
    "politica": "Decisão política redesenha regras e orçamentos. Quem ganha mandato ou verba com isso — e o que essa pessoa vai precisar comprar?",
    "energia": "Energia e clima são a camada de custo invisível da economia. Choques aqui chegam via inflação, frete e orçamento de TI.",
    "negocios": "Prática de gestão testada por quem está à frente. Destile uma ideia aplicável à SeeDs ou à sua operação comercial ainda esta semana.",
}

# ------------------------------------------------------------- coleta de RSS

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

TAG_RE = re.compile(r"<[^>]+>")
IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
OG_RE = re.compile(r'<meta[^>]+(?:property|name)=["\'](?:og:image(?::url)?|twitter:image(?::src)?)["\'][^>]+content=["\']([^"\']+)["\']'
                   r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image(?::url)?|twitter:image(?::src)?)["\']', re.I)
DESC_RE = re.compile(r'<meta[^>]+(?:property|name)=["\'](?:og:description|description|twitter:description)["\'][^>]+content=["\']([^"\']+)["\']'
                     r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:description|description|twitter:description)["\']', re.I)
BODY_LD_RE = re.compile(r'"articleBody"\s*:\s*"((?:[^"\\]|\\.){200,})"')
NUM_RE = re.compile(r'(?:US\$|R\$|\$|€|£)\s?\d[\d.,]*(?:\s?(?:bilh(?:ão|ões)|milh(?:ão|ões)|trilh(?:ão|ões)|mil\b|bi\b|mi\b|tri\b|billion|million|trillion|bn\b|k\b))?'
                    r'|\d+(?:[.,]\d+)?\s?%', re.I)

RUIDO = ["cookie", "subscribe", "newsletter", "sign up", "signup", "assine", "cadastre", "inscreva",
         "todos os direitos", "all rights reserved", "privacidade", "privacy policy", "terms of",
         "clique aqui", "leia também", "leia mais", "veja também", "veja mais", "siga o", "siga a",
         "follow us", "download the app", "getty images", "reprodução", "divulgação", "foto:", "image:",
         "advertisement", "publicidade", "compartilhe", "whatsapp do", "no telegram", "podcast", "©"]

STOP = set("""a o e de da do em um uma que com para por os as dos das no na nos nas ao à às aos se
sua seu suas seus como mais menos não sim já foi ser é são está estão tem têm pelo pela pelos pelas
entre sobre também depois antes quando onde qual quais isso essa esse esta este num numa mas ou nem
the an of to in and is are was were be been has have had for on with that this it its at by from
will would can could should may might about after before over under more most other new says said
according their they them his her she he we you your our us but not all one two out up down""".split())


def limpar_texto(s, limite=300):
    if not s:
        return ""
    s = htmllib.unescape(TAG_RE.sub(" ", s))
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > limite:
        s = s[:limite].rsplit(" ", 1)[0] + "…"
    return s


def cortar(s, n):
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def parse_data(s):
    if not s:
        return None
    for fn in (parsedate_to_datetime, lambda x: datetime.fromisoformat(x.strip().replace("Z", "+00:00"))):
        try:
            dt = fn(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None


def _texto(el, *tags):
    for t in tags:
        node = el.find(t)
        if node is not None and (node.text or "").strip():
            return node.text.strip()
    return ""


def _imagem_rss(item, desc_html):
    melhor, melhor_w = "", -1
    for path in ("media:content", "media:thumbnail", ".//media:content", ".//media:thumbnail"):
        for node in item.findall(path, NS):
            url = node.get("url")
            if not url or url.endswith(".mp3"):
                continue
            try:
                w = int(node.get("width") or 0)
            except ValueError:
                w = 0
            if w > melhor_w:
                melhor, melhor_w = url, w
    if melhor:
        return melhor, max(melhor_w, 0)
    enc = item.find("enclosure")
    if enc is not None:
        url = enc.get("url", "")
        if url and ("image" in enc.get("type", "") or re.search(r"\.(jpe?g|png|webp|gif)", url, re.I)):
            return url, 0
    m = IMG_RE.search(desc_html or "")
    return (m.group(1), 0) if m else ("", 0)


def melhorar_img(url):
    """Troca miniaturas conhecidas por versões maiores."""
    if not url:
        return url
    u = url
    u = re.sub(r"(ichef\.bbci\.co\.uk/(?:news|ace/standard)/)\d{2,4}(/)", r"\g<1>976\g<2>", u)
    if "aljazeera" in u and "?" in u:
        u = u.split("?")[0]
    u = re.sub(r"([?&](?:w|width)=)\d{2,3}(?=&|$)", r"\g<1>1200", u)
    u = re.sub(r"/fit-in/\d{2,3}x\d{2,3}/", "/fit-in/1080x608/", u)
    return u


def parse_feed(conteudo, feed):
    try:
        root = ET.fromstring(conteudo)
    except ET.ParseError:
        txt = conteudo.decode("utf-8", "ignore")
        txt = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", txt)
        try:
            root = ET.fromstring(txt)
        except ET.ParseError:
            return []

    itens = []
    rss_items = root.findall(".//item")
    if rss_items:
        for it in rss_items[:8]:
            titulo = limpar_texto(_texto(it, "title"), 200)
            link = _texto(it, "link") or (it.findtext("guid") or "").strip()
            desc_html = _texto(it, "description") or _texto(it, "{%s}encoded" % NS["content"])
            fonte = feed["fonte"]
            src = it.find("source")
            if src is not None and (src.text or "").strip():
                fonte = src.text.strip()
                titulo = re.sub(r"\s+-\s+" + re.escape(fonte) + r"$", "", titulo)
            img, img_w = _imagem_rss(it, desc_html)
            itens.append({
                "cat": feed["cat"], "fonte": fonte, "titulo": titulo, "link": link,
                "lang": feed.get("lang", "pt"),
                "resumo": limpar_texto(desc_html, 280),
                "dt": parse_data(_texto(it, "pubDate") or _texto(it, "{%s}date" % NS["dc"])),
                "img": img, "_imgw": img_w,
            })
    else:
        for e in root.findall("atom:entry", NS)[:8]:
            link = ""
            for ln in e.findall("atom:link", NS):
                if ln.get("rel") in (None, "alternate"):
                    link = ln.get("href", "")
                    break
            corpo = _texto(e, "{%s}summary" % NS["atom"]) or _texto(e, "{%s}content" % NS["atom"])
            img, img_w = _imagem_rss(e, corpo)
            itens.append({
                "cat": feed["cat"], "fonte": feed["fonte"],
                "titulo": limpar_texto(_texto(e, "{%s}title" % NS["atom"]), 200),
                "link": link,
                "lang": feed.get("lang", "pt"),
                "resumo": limpar_texto(corpo, 280),
                "dt": parse_data(_texto(e, "{%s}published" % NS["atom"]) or _texto(e, "{%s}updated" % NS["atom"])),
                "img": img, "_imgw": img_w,
            })
    return [i for i in itens if i["titulo"] and i["link"]]


def buscar_feed(feed):
    try:
        r = requests.get(feed["url"], headers=UA, timeout=15)
        r.raise_for_status()
        return parse_feed(r.content, feed)
    except Exception as exc:
        print(f"  [aviso] {feed['fonte']}: {type(exc).__name__}")
        return []


def normalizar(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return re.sub(r"[^a-z0-9 ]", "", s)


def coletar():
    print(f"Coletando {len(FEEDS)} feeds…")
    todos = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        for fut in as_completed([pool.submit(buscar_feed, f) for f in FEEDS]):
            todos.extend(fut.result())

    agora = datetime.now(timezone.utc)
    limite = agora - timedelta(days=6)
    vistos, itens = set(), []
    for it in sorted(todos, key=lambda x: x["dt"] or limite, reverse=True):
        if it["dt"] and it["dt"] > agora + timedelta(hours=2):
            it["dt"] = agora
        if it["dt"] and it["dt"] < limite:
            continue
        chave = normalizar(it["titulo"])[:60]
        if chave in vistos:
            continue
        vistos.add(chave)
        itens.append(it)

    por_cat, finais = {}, []
    for it in itens:
        n = por_cat.get(it["cat"], 0)
        if n < 12:
            por_cat[it["cat"]] = n + 1
            finais.append(it)
    print(f"Edição com {len(finais)} notícias.")
    return finais


# ----------------------------------------------- leitura completa da matéria

def extrair_artigo(url):
    """Baixa a matéria e devolve (parágrafos essenciais, og_image)."""
    try:
        r = requests.get(url, headers=UA, timeout=10)
        pagina = r.text
    except Exception:
        return [], ""

    og = ""
    m = OG_RE.search(pagina[:250000])
    if m:
        og = urljoin(url, htmllib.unescape(m.group(1) or m.group(2) or ""))

    def filtrar(paras):
        limpos = []
        for p in paras:
            t = limpar_texto(p, 620)
            if len(t) < 90:
                continue
            baixo = t.lower()
            if any(r_ in baixo for r_ in RUIDO):
                continue
            limpos.append(t)
            if len(limpos) >= 7:
                break
        return limpos

    # escada de extração: JSON-LD -> <p> dentro de <article> -> <p> global -> og:description
    limpos = []
    ld = BODY_LD_RE.search(pagina)
    if ld:
        try:
            corpo = json.loads('"' + ld.group(1) + '"')
        except Exception:
            corpo = ld.group(1).replace('\\"', '"').replace("\\n", "\n")
        blocos = [b.strip() for b in re.split(r"\n+", corpo) if b.strip()]
        if len(blocos) <= 1:
            frases = re.split(r"(?<=[.!?])\s+", corpo)
            blocos = [" ".join(frases[i:i + 3]) for i in range(0, len(frases), 3)]
        limpos = filtrar(blocos)
    if not limpos:
        corpo = re.sub(r"(?is)<(script|style|noscript|svg|form|nav|header|footer|aside|figure)[^>]*>.*?</\1>", " ", pagina)
        escopo = re.search(r"(?is)<article[^>]*>(.*?)</article>", corpo)
        if escopo:
            limpos = filtrar(re.findall(r"(?is)<p[^>]*>(.*?)</p>", escopo.group(1)))
        if not limpos:
            limpos = filtrar(re.findall(r"(?is)<p[^>]*>(.*?)</p>", corpo))
    if not limpos:
        m = DESC_RE.search(pagina[:250000])
        if m:
            desc = limpar_texto(htmllib.unescape(m.group(1) or m.group(2) or ""), 620)
            if len(desc) >= 110:
                limpos = [desc]
    return limpos, og


def ler_artigos(itens):
    alvo = [i for i in itens if "news.google" not in i["link"]]
    print(f"Lendo {len(alvo)} matérias completas (essência local + imagens em alta)…")
    with ThreadPoolExecutor(max_workers=12) as pool:
        futuros = {pool.submit(extrair_artigo, i["link"]): i for i in alvo}
        for fut in as_completed(futuros):
            it = futuros[fut]
            paras, og = fut.result()
            it["leitura"] = paras
            if og and (not it["img"] or (0 < it["_imgw"] < 500)):
                if it["img"] and it["img"] != og:
                    it["_imgalt"] = it["img"]
                it["img"] = og
    for it in itens:
        it.setdefault("leitura", [])
        it.setdefault("_imgalt", "")


# ------------------------------------------- leitura estratégica em três atos

def _palavras(s):
    return [w for w in re.findall(r"[a-zà-ü0-9]+", s.lower()) if w not in STOP and len(w) > 2]


def frases_chave(paras, titulo, resumo, max_chars=440):
    """Resumo extrativo: as frases mais informativas da própria matéria."""
    texto = " ".join(paras) if paras else (resumo or "")
    if not texto:
        return ""
    frases = [f.strip() for f in re.split(r'(?<=[.!?])\s+(?=[A-ZÀ-Ü0-9"“«])', texto)
              if 60 <= len(f.strip()) <= 340][:40]
    if not frases:
        return cortar(texto, max_chars)
    freq = {}
    for f in frases:
        for w in _palavras(f):
            freq[w] = freq.get(w, 0) + 1
    tw = set(_palavras(titulo))

    def score(i):
        ws = _palavras(frases[i])
        if not ws:
            return 0.0
        base = sum(freq.get(w, 0) for w in ws) / (len(ws) ** 0.5)
        return base * (1.35 if i < 6 else 1.0) + 3 * len(tw & set(ws))

    melhores = sorted(sorted(range(len(frases)), key=lambda i: -score(i))[:3])
    out = " ".join(frases[i] for i in melhores)
    return cortar(out, max_chars)


def citacao_curta(paras, titulo, max_chars=170):
    """Uma única frase citada, entre aspas e com crédito à fonte — modelo de citação
    curta com atribuição (LDA art. 46), seguro para publicação: nunca reescreve nem
    reproduz parágrafos inteiros, só credita um trecho pontual."""
    texto = " ".join(paras) if paras else ""
    if not texto:
        return ""
    frases = [f.strip() for f in re.split(r'(?<=[.!?])\s+(?=[A-ZÀ-Ü0-9"“«])', texto)
              if 50 <= len(f.strip()) <= max_chars][:20]
    if not frases:
        return ""
    freq = {}
    for f in frases:
        for w in _palavras(f):
            freq[w] = freq.get(w, 0) + 1
    tw = set(_palavras(titulo))

    def score(i):
        ws = _palavras(frases[i])
        if not ws:
            return 0.0
        base = sum(freq.get(w, 0) for w in ws) / (len(ws) ** 0.5)
        return base * (1.3 if i < 5 else 1.0) + 2 * len(tw & set(ws))

    melhor = frases[max(range(len(frases)), key=score)].strip().strip('"“”')
    if not melhor or normalizar(melhor) == normalizar(titulo):
        return ""
    return melhor  # frase pura, sem aspas/crédito — isso é aplicado no export (formatar_citacao)


def formatar_citacao(frase, fonte):
    return f"«{frase}» — trecho de: {fonte}" if frase else ""


def extrair_numeros(texto):
    achados = []
    for m in NUM_RE.finditer(texto):
        v = re.sub(r"\s+", " ", m.group(0).strip())
        if v not in achados and len(v) > 1:
            achados.append(v)
    return achados[:4]


def detectar_temas(titulo, corpo):
    """Palavra no título vale dobro; só classifica com pontuação mínima 2 —
    evita que uma palavra ambígua no corpo dispare o tema errado."""
    t_low = " " + titulo.lower() + " "
    c_low = " " + corpo.lower() + " "
    placar = {}
    for chave, tema in TEMAS.items():
        pts = 0
        for kw in tema["kw"]:
            if kw in t_low:
                pts += 2
            elif kw in c_low:
                pts += 1
        if pts >= 2:
            placar[chave] = pts
    return [k for k, _ in sorted(placar.items(), key=lambda kv: -kv[1])][:3]


def _titulo_pt(item):
    return (item.get("pt") or {}).get("titulo") or item["titulo"]


def frase_conexao(it, itens):
    """Explica como esta matéria conversa com as conexões mostradas abaixo."""
    for j in it["rel"]:
        shared = it["_temas_key"] & itens[j]["_temas_key"]
        if shared:
            tkey = sorted(shared)[0]
            tema, outro = TEMAS[tkey], itens[j]
            efeito = tema["correl"][0]["efeito"] if tema["correl"] else ""
            return (f"Leia em par com «{cortar(_titulo_pt(outro), 72)}» ({outro['fonte']}), nas conexões abaixo: "
                    f"os dois puxam o mesmo fio — {tema['label'].lower()}. {efeito}")
    if it["rel"]:
        outro = itens[it["rel"][0]]
        return (f"Dialoga com «{cortar(_titulo_pt(outro), 72)}» ({outro['fonte']}), nas conexões abaixo — "
                "mesmo tabuleiro. Compare os dois movimentos antes de fechar opinião.")
    return ""


def gerar_inteligencia(itens):
    labels = dict(CATEGORIAS)
    for it in itens:
        temas = detectar_temas(it["titulo"], it["resumo"] + " " + " ".join(it["leitura"][:3]))
        it["temas"] = [TEMAS[t]["label"] for t in temas]
        it["_temas_key"] = set(temas)
        seed = int(hashlib.md5(it["titulo"].encode()).hexdigest(), 16)
        if temas:
            principal = TEMAS[temas[0]]
            portras = principal["insights"][seed % len(principal["insights"])]
        else:
            portras = FALLBACK_INSIGHT[it["cat"]]
        it["_portras"] = portras

        correl, vistos = [], set()
        for t in temas:
            for c in TEMAS[t]["correl"]:
                if c["tema"] not in vistos:
                    vistos.add(c["tema"])
                    correl.append({"tema": c["tema"], "efeito": c["efeito"],
                                   "onde": [{"nome": n, "url": u} for n, u in c["onde"]]})
        it["correl"] = correl[:4]

    # conexões (temas em comum; senão, mesma categoria)
    for i, it in enumerate(itens):
        pontos = []
        for j, outro in enumerate(itens):
            if i == j:
                continue
            score = 2 * len(it["_temas_key"] & outro["_temas_key"]) + (1 if it["cat"] == outro["cat"] else 0)
            if score:
                pontos.append((score, j))
        pontos.sort(key=lambda p: -p[0])
        it["rel"] = [j for _, j in pontos[:3]]

    # três atos (a conexão é fechada depois da tradução, em conectar())
    for it in itens:
        diz = frases_chave(it["leitura"], it["titulo"], it["resumo"])
        n_diz, n_tit = normalizar(diz), normalizar(it["titulo"])
        if n_diz and (n_diz == n_tit or (n_tit in n_diz and len(n_diz) <= len(n_tit) + 25)):
            diz = ""  # "a matéria diz" que só repete a manchete não agrega
        it["digest"] = {
            "diz": diz,
            "citacao": citacao_curta(it["leitura"], it["titulo"]),
            "portras": it["_portras"],
            "conexao": "",
            "numeros": extrair_numeros(it["titulo"] + " " + it["resumo"] + " " + " ".join(it["leitura"])),
        }


# ------------------------------------------------- Top News (curadoria John)
# O que alguém de estratégia, tecnologia, IA e empreendedorismo precisa saber.

PESO_TEMA = {"ia_generativa": 5, "negocio_ia": 5, "chips": 4, "startups": 4, "vendas_growth": 4,
             "bigtech": 3, "telecom": 3, "ma": 3, "regulacao": 2, "mercados": 2,
             "juros_inflacao": 2, "trabalho": 2, "geopolitica": 2}
PESO_CAT = {"ia": 4, "ia_negocios": 4, "empreendedorismo": 3, "vendas": 3,
            "tecnologia": 3, "negocios": 2, "economia": 1}


def marcar_top(itens, quantos=15):
    agora = datetime.now(timezone.utc)
    for it in itens:
        s = PESO_CAT.get(it["cat"], 0) + sum(PESO_TEMA.get(t, 1) for t in it["_temas_key"])
        if it["dt"] and (agora - it["dt"]) < timedelta(hours=24):
            s += 2
        if it["digest"]["numeros"]:
            s += 1
        s += min(len(it["leitura"]), 3)  # essência rica desempata
        it["_score"] = s
        it["top"] = False
    # Top News exige essência da matéria disponível
    candidatos = sorted((i for i in itens if i["leitura"]), key=lambda x: -x["_score"])
    for it in candidatos[:quantos]:
        it["top"] = True
    print(f"Top News: {min(quantos, len(candidatos))} matérias marcadas (todas com essência).")


# ------------------------------------------ tradução EN -> PT (com cache)

TRAD_LOCK = threading.Lock()
TRAD_SEP = "\n||\n"
TRAD_SPLIT = re.compile(r"\n?\s*\|\s*\|+\s*\n?")


def _google_trad(texto):
    try:
        r = requests.post("https://translate.googleapis.com/translate_a/single",
                          data={"client": "gtx", "sl": "auto", "tl": "pt-BR", "dt": "t", "q": texto},
                          headers=UA, timeout=15)
        dados = r.json()
        return "".join(seg[0] for seg in dados[0] if seg and seg[0])
    except Exception:
        return ""


def traduzir_lote(textos, cache):
    """Traduz uma lista de textos, usando cache por hash e 1 chamada por lote."""
    out = [t for t in textos]
    pendentes = []
    with TRAD_LOCK:
        for i, t in enumerate(textos):
            if not t or not t.strip():
                continue
            h = hashlib.md5(t.encode()).hexdigest()
            if h in cache:
                out[i] = cache[h]
            else:
                pendentes.append(i)
    if pendentes:
        trad = _google_trad(TRAD_SEP.join(textos[i] for i in pendentes))
        partes = [p.strip() for p in TRAD_SPLIT.split(trad)] if trad else []
        if len(partes) != len(pendentes):
            partes = []
            for i in pendentes:
                t1 = _google_trad(textos[i]).strip()
                partes.append(t1 or textos[i])
        with TRAD_LOCK:
            for k, i in enumerate(pendentes):
                if partes[k]:
                    out[i] = partes[k]
                cache[hashlib.md5(textos[i].encode()).hexdigest()] = out[i]
    return out


def traduzir_edicao(itens):
    cache_path = BASE / "data" / "trad_cache.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    alvos = [it for it in itens if it["lang"] == "en"]
    print(f"Traduzindo {len(alvos)} matérias em inglês para PT…")

    def worker(it):
        campos = traduzir_lote([it["titulo"], it["resumo"], it["digest"]["diz"], it["digest"]["citacao"]], cache)
        pt = {"titulo": campos[0], "resumo": campos[1], "diz": campos[2], "citacao": campos[3], "leitura": []}
        if it["leitura"]:
            pt["leitura"] = traduzir_lote(it["leitura"], cache)
        it["pt"] = pt

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(worker, alvos))

    falhas = sum(1 for it in alvos if it.get("pt", {}).get("titulo") == it["titulo"])
    if falhas > len(alvos) // 2 and alvos:
        print(f"  [aviso] {falhas} títulos ficaram iguais — serviço de tradução pode estar limitado.")
    try:
        cache_path.parent.mkdir(exist_ok=True)
        if len(cache) > 4000:
            cache = dict(list(cache.items())[-4000:])
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def conectar(itens):
    """Fecha o ato 3 (conexão) usando títulos já traduzidos e limpa temporários."""
    for it in itens:
        it["digest"]["conexao"] = frase_conexao(it, itens)
    for it in itens:
        del it["_temas_key"], it["_portras"]
        it.pop("_score", None)


def enriquecer_com_claude(itens):
    """Opcional (--ai): reescreve a leitura estratégica com a API da Anthropic."""
    try:
        import anthropic
    except ImportError:
        print("[ai] SDK não instalado — rode: pip install anthropic. Usando motor local.")
        return
    client = anthropic.Anthropic()
    sistema = (
        "Você escreve leituras estratégicas curtas (2 a 3 frases, pt-BR) para John, "
        "estrategista de vendas na TIM Brasil e cofundador da consultoria SeeDs.AI. "
        "Tom maduro, direto, sem hype e sem exclamações. Explique o que está por trás "
        "da notícia e o que merece atenção, conectando a uma implicação prática de "
        "estratégia, vendas ou posicionamento."
    )
    schema = {"type": "object", "additionalProperties": False, "required": ["itens"],
              "properties": {"itens": {"type": "array", "items": {
                  "type": "object", "additionalProperties": False,
                  "required": ["i", "insight"],
                  "properties": {"i": {"type": "integer"}, "insight": {"type": "string"}}}}}}
    for inicio in range(0, len(itens), 20):
        lote = itens[inicio:inicio + 20]
        pauta = [{"i": inicio + k, "titulo": it["titulo"],
                  "materia": " ".join(it["leitura"])[:1500] or it["resumo"],
                  "categoria": it["cat"]} for k, it in enumerate(lote)]
        try:
            resp = client.messages.create(
                model="claude-opus-4-8",
                max_tokens=16000,
                system=sistema,
                output_config={"format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": "Gere a leitura 'por trás disso' por item:\n" + json.dumps(pauta, ensure_ascii=False)}],
            )
            texto = next(b.text for b in resp.content if b.type == "text")
            for reg in json.loads(texto)["itens"]:
                if 0 <= reg["i"] < len(itens) and reg["insight"].strip():
                    itens[reg["i"]]["digest"]["portras"] = reg["insight"].strip()
            print(f"[ai] Lote {inicio // 20 + 1} enriquecido.")
        except Exception as exc:
            print(f"[ai] Lote {inicio // 20 + 1} falhou ({type(exc).__name__}); mantendo motor local.")


# ------------------------------------------------------------ assets & saída

def _b64_imagem(caminho, max_px, nome_cache):
    cache = BASE / "assets" / f"{nome_cache}.b64"
    try:
        from PIL import Image
        im = Image.open(caminho)
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        dado = base64.b64encode(buf.getvalue()).decode()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(dado)
        return dado
    except Exception:
        return cache.read_text() if cache.exists() else ""


def carregar_assets():
    return {
        "logo": _b64_imagem(MIDIA / "Logo.png", 360, "logo"),
        "folha": _b64_imagem(MIDIA / "Folha.png", 220, "folha"),
        "clara": _b64_imagem(MIDIA / "Clara.png", 200, "clara"),
    }


MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def gerar_edicao(usar_ai=False, publico=False):
    itens = coletar()
    if not itens:
        print("Nenhuma notícia coletada — mantendo edição anterior.")
        return False
    ler_artigos(itens)
    gerar_inteligencia(itens)
    marcar_top(itens)
    traduzir_edicao(itens)
    conectar(itens)
    if usar_ai:
        enriquecer_com_claude(itens)

    agora = datetime.now()
    labels = dict(CATEGORIAS)
    dados = {
        "geradoTs": int(time.time() * 1000),
        "geradoLabel": f"{agora.day} de {MESES[agora.month - 1]} · {agora:%H}h{agora:%M}",
        "intervaloHoras": INTERVALO_HORAS,
        "publico": publico,
        "ctaUrl": CTA_ASSINE_URL,
        "categorias": [{"id": c, "label": l} for c, l in CATEGORIAS],
        "itens": [],
    }
    for k, it in enumerate(itens):
        img_final = melhorar_img(it["img"])
        img_alt = it["_imgalt"] or (it["img"] if img_final != it["img"] else "")
        digest = dict(it["digest"])
        pt = dict(it["pt"]) if it.get("pt") else None
        leitura = it["leitura"]
        citacao = digest.pop("citacao", "")
        pt_citacao = pt.pop("citacao", "") if pt else ""
        if publico:
            # modo publicação: nunca reproduz parágrafos da matéria — troca por
            # citação curta com crédito (LDA art. 46). Essência completa fica só
            # na edição pessoal (sem --publico).
            digest["diz"] = formatar_citacao(citacao, it["fonte"])
            leitura = []
            if pt:
                pt["diz"] = formatar_citacao(pt_citacao or citacao, it["fonte"])
                pt["leitura"] = []
        dados["itens"].append({
            "id": k, "cat": it["cat"], "catLabel": labels[it["cat"]],
            "fonte": it["fonte"], "titulo": it["titulo"], "resumo": it["resumo"],
            "link": it["link"], "img": img_final, "imgAlt": img_alt,
            "ts": int(it["dt"].timestamp() * 1000) if it["dt"] else None,
            "lang": it["lang"], "top": it["top"], "pt": pt,
            "temas": it["temas"], "digest": digest,
            "leitura": leitura, "correl": it["correl"], "rel": it["rel"],
        })

    out_dir = (BASE / "docs") if publico else BASE
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    (out_dir / "data" / "noticias.json").write_text(
        json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")

    assets = carregar_assets()
    if publico:
        (out_dir / "assets").mkdir(parents=True, exist_ok=True)
        (out_dir / "assets" / "logo.png").write_bytes(base64.b64decode(assets["logo"]))

    html_final = (HTML_TMPL
                  .replace("__LOGO__", assets["logo"])
                  .replace("__FOLHA__", assets["folha"])
                  .replace("__CLARA__", assets["clara"])
                  .replace("__DATA__", json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")))
    (out_dir / "index.html").write_text(html_final, encoding="utf-8")
    print(f"{out_dir / 'index.html'} gerado — {len(itens)} notícias · {agora:%d/%m/%Y %H:%M}"
          + (" [PÚBLICO — docs/]" if publico else ""))
    return True


# ------------------------------------------------------------------ template

HTML_TMPL = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SeeDs Radar</title>
<meta name="description" content="Curadoria de IA, tecnologia, economia e negócios com leitura estratégica SeeDs.AI — atualizado automaticamente.">
<meta property="og:type" content="website">
<meta property="og:site_name" content="SeeDs Radar">
<meta property="og:title" content="SeeDs Radar — inteligência estratégica em tempo real">
<meta property="og:description" content="Curadoria de IA, tecnologia, economia e negócios com leitura estratégica SeeDs.AI — atualizado automaticamente a cada poucas horas.">
<meta property="og:image" content="assets/logo.png">
<meta name="twitter:card" content="summary">
<link rel="icon" href="data:image/png;base64,__LOGO__">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,500;9..144,600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#f5f8fc; --surface:#ffffff; --surface-2:#eef3fa; --surface-3:#e3ecf6;
  --blue-50:#eaf2fc; --blue-100:#d4e4fa; --blue-200:#a8c8f0; --blue-300:#6fa6e6;
  --blue-400:#3b82f6; --blue-500:#2563eb; --blue-600:#1d4ed8; --blue-700:#1e3a8a; --blue-900:#0b1f4a;
  --leaf:#14b8a6; --leaf-soft:#99f6e4;
  --ink:#0f1e3d; --ink-2:#324971; --mute:#5d7493; --soft:#93a4be;
  --line:#d8e3f1; --line-2:#c2d3e8;
  --grad-blue:linear-gradient(135deg,#2563eb 0%,#3b82f6 55%,#0ea5e9 100%);
  --sh-1:0 1px 2px rgba(11,31,74,.05),0 4px 14px rgba(11,31,74,.05);
  --sh-2:0 6px 14px rgba(37,99,235,.12),0 18px 40px rgba(11,31,74,.12);
}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--ink-2);font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
button{font-family:'Inter',sans-serif}
.atmos{position:fixed;inset:0;z-index:0;pointer-events:none;background:
  radial-gradient(ellipse 80% 60% at 12% 0%,rgba(37,99,235,.07),transparent 55%),
  radial-gradient(ellipse 70% 55% at 92% 100%,rgba(20,184,166,.05),transparent 55%)}
.circuit{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.35;background-image:
  linear-gradient(rgba(37,99,235,.06) 1px,transparent 1px),
  linear-gradient(90deg,rgba(37,99,235,.06) 1px,transparent 1px);
  background-size:56px 56px;
  mask-image:radial-gradient(ellipse 80% 60% at 50% 0%,#000 20%,transparent 75%);
  -webkit-mask-image:radial-gradient(ellipse 80% 60% at 50% 0%,#000 20%,transparent 75%)}

/* ---- intro ---- */
#intro{position:fixed;inset:0;z-index:9999;background:#ffffff;display:flex;flex-direction:column;align-items:center;justify-content:center;animation:inFade .5s ease both}
#intro img{width:min(46vmin,260px);animation:logoRise 1.6s cubic-bezier(.2,.7,.2,1) both}
#intro .tag{margin-top:26px;font-size:11px;letter-spacing:.42em;text-transform:uppercase;color:#94a3b8;font-weight:500;animation:tagIn 1.4s .5s ease both}
#intro.out{animation:outFade .9s ease forwards}
@keyframes inFade{from{opacity:0}to{opacity:1}}
@keyframes outFade{from{opacity:1}to{opacity:0;visibility:hidden}}
@keyframes logoRise{from{opacity:0;transform:scale(.86) translateY(14px)}to{opacity:1;transform:scale(1) translateY(0)}}
@keyframes tagIn{from{opacity:0;letter-spacing:.6em}to{opacity:1;letter-spacing:.42em}}

/* ---- header ---- */
header{position:sticky;top:0;z-index:60;background:rgba(245,248,252,.86);backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
.top{max-width:1280px;margin:0 auto;padding:13px 28px;display:flex;align-items:center;justify-content:space-between;gap:16px}
.brand{display:flex;align-items:center;gap:13px}
.brand img{width:42px;height:42px;object-fit:contain}
.brand-name{font-family:'Fraunces',serif;font-size:22px;color:var(--blue-900);line-height:1.1}
.brand-name b{color:var(--blue-500);font-weight:600}
.brand-sub{font-size:10px;letter-spacing:.24em;text-transform:uppercase;color:var(--mute);font-weight:600}
.edition{display:flex;align-items:center;gap:9px;font-size:12.5px;color:var(--mute);background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:7px 15px;white-space:nowrap}
.edition .dot{width:7px;height:7px;border-radius:50%;background:var(--leaf);animation:pulse 2.4s infinite}
@keyframes pulse{0%,100%{box-shadow:0 0 0 3px rgba(20,184,166,.18)}50%{box-shadow:0 0 0 7px rgba(20,184,166,.05)}}

main{max-width:1280px;margin:0 auto;padding:0 28px 60px;position:relative;z-index:1}
.eyebrow{font-size:11px;letter-spacing:.28em;text-transform:uppercase;color:var(--blue-500);font-weight:600}

/* ---- panorama: radar + temas quentes ---- */
.panorama{display:grid;grid-template-columns:230px 1fr;gap:34px;align-items:center;padding:30px 0 8px}
.radar{position:relative;width:212px;height:212px;border-radius:50%;background:radial-gradient(circle,#fff 0%,var(--blue-50) 78%);border:1px solid var(--line-2);box-shadow:var(--sh-1)}
.radar .ring{position:absolute;border:1px solid rgba(37,99,235,.16);border-radius:50%}
.radar .r1{inset:18%}.radar .r2{inset:36%}.radar .r3{inset:8%}
.radar .cross{position:absolute;inset:0;background:
  linear-gradient(rgba(37,99,235,.10),rgba(37,99,235,.10)) 50% 0/1px 100% no-repeat,
  linear-gradient(rgba(37,99,235,.10),rgba(37,99,235,.10)) 0 50%/100% 1px no-repeat;border-radius:50%}
.radar .sweep{position:absolute;inset:0;border-radius:50%;overflow:hidden;
  background:conic-gradient(from 0deg,rgba(37,99,235,.30),rgba(37,99,235,.06) 55deg,transparent 80deg);
  animation:gira 5s linear infinite}
@keyframes gira{to{transform:rotate(360deg)}}
.radar .core{position:absolute;left:50%;top:50%;width:46px;height:46px;transform:translate(-50%,-50%);border-radius:50%;background:url('data:image/png;base64,__FOLHA__') center/32px no-repeat,#fff;border:1px solid var(--line);box-shadow:var(--sh-1)}
.blip{position:absolute;width:12px;height:12px;border:none;border-radius:50%;background:var(--blue-500);transform:translate(-50%,-50%);cursor:pointer;animation:blipPulse 2.6s infinite}
.blip:nth-child(even){background:var(--leaf)}
.blip:hover{transform:translate(-50%,-50%) scale(1.5)}
@keyframes blipPulse{0%,100%{box-shadow:0 0 0 0 rgba(37,99,235,.35)}55%{box-shadow:0 0 0 9px rgba(37,99,235,0)}}
.pan-title{font-family:'Fraunces',serif;font-weight:400;font-size:clamp(24px,3vw,36px);color:var(--blue-900);margin:8px 0 14px}
.pan-title em{font-style:italic;color:var(--blue-500);font-weight:500}
.hot{display:flex;flex-wrap:wrap;gap:9px}
.hot-chip{display:flex;flex-direction:column;align-items:flex-start;gap:1px;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:9px 15px;cursor:pointer;transition:.2s;text-align:left}
.hot-chip:hover{border-color:var(--blue-300);box-shadow:var(--sh-1);transform:translateY(-2px)}
.hot-chip b{font-family:'Fraunces',serif;font-weight:600;font-size:14px;color:var(--blue-900)}
.hot-chip span{font-size:10.5px;color:var(--mute);letter-spacing:.06em;text-transform:uppercase;font-weight:600}

/* ---- filtros ---- */
.filters{position:sticky;top:69px;z-index:50;background:rgba(245,248,252,.9);backdrop-filter:blur(12px);padding:12px 0;display:flex;gap:12px;align-items:center}
.pills{display:flex;gap:8px;flex:1;overflow-x:auto;scrollbar-width:none;padding-bottom:2px}
.pills::-webkit-scrollbar{display:none}
.pill{flex-shrink:0;border:1px solid var(--line-2);background:var(--surface);color:var(--ink-2);border-radius:999px;padding:7px 15px;font-size:13px;font-weight:500;cursor:pointer;transition:.2s;display:flex;gap:7px;align-items:center}
.pill small{color:var(--soft);font-weight:600;font-size:11px}
.pill:hover{border-color:var(--blue-300);color:var(--blue-600)}
.pill.on{background:var(--grad-blue);border-color:transparent;color:#fff;box-shadow:0 4px 12px rgba(37,99,235,.28)}
.pill.on small{color:rgba(255,255,255,.75)}
#busca{border:1px solid var(--line-2);background:var(--surface);border-radius:999px;padding:9px 18px;font-size:13.5px;font-family:'Inter',sans-serif;color:var(--ink);width:230px;outline:none;transition:.2s;flex-shrink:0}
#busca:focus{border-color:var(--blue-400);box-shadow:0 0 0 3px rgba(59,130,246,.12)}
.ptbtn{flex-shrink:0;display:flex;align-items:center;gap:8px;border:1px solid var(--line-2);background:var(--surface);border-radius:999px;padding:8px 14px;font-size:12px;font-weight:700;letter-spacing:.04em;color:var(--mute);cursor:pointer;transition:.2s}
.ptbtn .sw{width:30px;height:16px;border-radius:999px;background:var(--line-2);position:relative;transition:.2s}
.ptbtn .knob{position:absolute;top:2px;left:2px;width:12px;height:12px;border-radius:50%;background:#fff;transition:.2s;box-shadow:0 1px 3px rgba(11,31,74,.3)}
.ptbtn.on{border-color:var(--blue-300);color:var(--blue-600)}
.ptbtn.on .sw{background:var(--grad-blue)}
.ptbtn.on .knob{left:16px}
.pill-top{border-color:rgba(20,184,166,.55);color:#0f766e;font-weight:600}
.pill-top small{color:#14b8a6}
.pill-top.on{background:linear-gradient(135deg,#14b8a6 0%,#0ea5e9 100%);border-color:transparent;color:#fff;box-shadow:0 4px 12px rgba(20,184,166,.3)}
.pill-top.on small{color:rgba(255,255,255,.8)}
.chip.topc{background:linear-gradient(135deg,#14b8a6,#0ea5e9);color:#fff}
.meta.luz .chip.topc{background:linear-gradient(135deg,#14b8a6,#0ea5e9);color:#fff;backdrop-filter:none}
.trad-note{font-size:11px;color:var(--soft);font-style:italic;margin-left:10px}
.assine-btn{display:inline-flex;align-items:center;gap:8px;margin-top:16px;padding:12px 22px;border-radius:999px;background:var(--grad-blue);color:#fff;font-weight:600;font-size:13.5px;text-decoration:none;box-shadow:0 6px 16px rgba(37,99,235,.28);transition:.2s}
.assine-btn:hover{transform:translateY(-2px);box-shadow:0 10px 22px rgba(37,99,235,.35)}
.assine-btn.mini{margin-top:0;padding:8px 16px;font-size:12.5px}

/* ---- mosaico bento ---- */
.sec-head{display:flex;align-items:baseline;justify-content:space-between;margin:20px 0 16px}
.bento{display:grid;grid-template-columns:repeat(6,1fr);grid-auto-rows:152px;gap:16px;grid-auto-flow:dense}
.tile{position:relative;border-radius:16px;overflow:hidden;cursor:pointer;background:var(--surface);border:1px solid var(--line);box-shadow:var(--sh-1);transition:transform .25s,box-shadow .25s,border-color .25s,opacity .5s;opacity:0;transform:translateY(16px)}
.tile.vis{opacity:1;transform:none}
.tile:hover{transform:translateY(-4px);box-shadow:var(--sh-2);border-color:var(--blue-200)}
.t-hero{grid-column:span 4;grid-row:span 2}
.t-tall{grid-column:span 2;grid-row:span 2}
.t-wide{grid-column:span 3;grid-row:span 2}
.t-brief{grid-column:span 2;grid-row:span 1}
.tile img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;transition:transform .6s cubic-bezier(.2,.7,.2,1)}
.tile:hover img{transform:scale(1.05)}
.tile .scrim{position:absolute;inset:0;background:linear-gradient(180deg,rgba(11,31,74,.06) 30%,rgba(11,31,74,.62) 72%,rgba(11,31,74,.88) 100%)}
.tile .tc{position:absolute;inset:auto 0 0 0;padding:18px 20px;display:flex;flex-direction:column;gap:8px}
.tile h3{font-family:'Fraunces',serif;font-weight:500;color:#fff;line-height:1.28;font-size:17px;text-wrap:balance}
.t-hero h3{font-size:clamp(19px,2.2vw,26px)}
.tile .tz{font-size:12.5px;color:rgba(255,255,255,.82);line-height:1.5;max-width:60ch}
.tile.semimg img{display:none}
.tile.semimg{background:var(--grad-blue)}
.tile.semimg .scrim{background:linear-gradient(180deg,rgba(11,31,74,0) 40%,rgba(11,31,74,.35))}
.meta{display:flex;flex-wrap:wrap;gap:7px;align-items:center}
.chip{font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--blue-600);background:var(--blue-50);border-radius:6px;padding:3px 9px}
.src{font-size:11.5px;color:var(--mute);font-weight:600}
.ago{font-size:11.5px;color:var(--soft)}
.meta.luz .chip{background:rgba(255,255,255,.18);color:#fff;backdrop-filter:blur(4px)}
.meta.luz .src{color:rgba(255,255,255,.85)}
.meta.luz .ago{color:rgba(255,255,255,.6)}
.t-brief{padding:15px 17px;display:flex;flex-direction:column;gap:8px;justify-content:flex-start}
.t-brief h4{font-family:'Fraunces',serif;font-weight:500;font-size:14.5px;color:var(--blue-900);line-height:1.35;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.t-brief:hover h4{color:var(--blue-600)}
.vazio{padding:60px 20px;text-align:center;color:var(--mute);font-size:14px;grid-column:1/-1}

/* ---- modal ---- */
#overlay{position:fixed;inset:0;z-index:200;background:rgba(11,31,74,.45);backdrop-filter:blur(6px);display:none;align-items:flex-start;justify-content:center;padding:4vh 18px;overflow-y:auto}
#overlay.show{display:flex;animation:inFade .25s ease}
#modal{background:var(--bg);border-radius:20px;max-width:920px;width:100%;overflow:hidden;box-shadow:0 30px 80px rgba(11,31,74,.35);animation:up .3s cubic-bezier(.2,.7,.2,1)}
@keyframes up{from{opacity:0;transform:translateY(22px)}to{opacity:1;transform:none}}
.m-head{position:relative;min-height:90px;background:linear-gradient(135deg,var(--blue-50),var(--surface-3)) url('data:image/png;base64,__FOLHA__') center/80px no-repeat}
.m-head img{width:100%;max-height:340px;object-fit:cover;display:block;position:relative}
.m-close{position:absolute;top:14px;right:14px;width:36px;height:36px;border-radius:50%;border:none;background:rgba(255,255,255,.92);color:var(--blue-900);font-size:17px;cursor:pointer;box-shadow:var(--sh-1);z-index:2}
.m-body{padding:26px 36px 36px;display:flex;flex-direction:column;gap:18px}
.m-body h2{font-family:'Fraunces',serif;font-weight:500;font-size:clamp(20px,2.4vw,27px);color:var(--blue-900);line-height:1.28}
.fonte-link{display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:600;color:var(--blue-500);text-decoration:none}
.fonte-link:hover{text-decoration:underline}

/* leitura da Clara em três atos */
.clara{background:linear-gradient(135deg,rgba(37,99,235,.055),rgba(20,184,166,.04));border:1px solid var(--blue-100);border-radius:16px;padding:20px 22px;display:flex;flex-direction:column;gap:14px}
.clara-h{display:flex;align-items:center;gap:12px}
.clara-h img{width:44px;height:44px;border-radius:50%;object-fit:cover;border:2px solid #fff;box-shadow:var(--sh-1)}
.clara-h .lb{font-size:10.5px;letter-spacing:.2em;text-transform:uppercase;color:var(--blue-600);font-weight:700}
.clara-h .lb2{font-size:11.5px;color:var(--mute)}
.passo{display:grid;grid-template-columns:118px 1fr;gap:14px;align-items:start}
.ptag{font-size:9.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:#fff;background:var(--grad-blue);border-radius:6px;padding:4px 8px;text-align:center;margin-top:2px}
.passo:nth-child(4) .ptag{background:linear-gradient(135deg,#14b8a6,#0ea5e9)}
.passo p{font-size:13.5px;color:var(--ink);line-height:1.62}
.nums{display:flex;flex-wrap:wrap;gap:7px;padding-left:132px}
.nums span{font-family:'Fraunces',serif;font-weight:600;font-size:13px;color:var(--blue-700);background:#fff;border:1px solid var(--blue-100);border-radius:8px;padding:4px 11px}

/* essência da matéria (anti-paywall local) */
.leitura{background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.leitura summary{cursor:pointer;padding:15px 20px;font-size:13.5px;font-weight:600;color:var(--blue-700);list-style:none;display:flex;align-items:center;gap:9px}
.leitura summary::before{content:"›";font-size:17px;color:var(--blue-400);transition:transform .2s}
.leitura[open] summary::before{transform:rotate(90deg)}
.leitura summary small{color:var(--mute);font-weight:400}
.leitura .lp{padding:2px 22px 18px;display:flex;flex-direction:column;gap:11px}
.leitura .lp p{font-size:13.5px;color:var(--ink-2);line-height:1.7}
.leitura .lp p:first-child::first-letter{font-family:'Fraunces',serif;font-size:30px;color:var(--blue-500);float:left;line-height:1;padding-right:7px}

.temas{display:flex;flex-wrap:wrap;gap:7px}
.tema-chip{font-size:11.5px;font-weight:600;color:var(--ink-2);background:var(--surface);border:1px solid var(--line-2);border-radius:999px;padding:4px 12px;cursor:pointer;transition:.2s}
.tema-chip:hover{border-color:var(--leaf);color:var(--leaf)}
.sec-t{font-size:11px;letter-spacing:.26em;text-transform:uppercase;color:var(--blue-500);font-weight:700}
.correl-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:11px}
.correl{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.correl .t{font-family:'Fraunces',serif;font-size:14.5px;font-weight:600;color:var(--blue-900);margin-bottom:5px}
.correl .e{font-size:12.5px;color:var(--mute);line-height:1.5;margin-bottom:9px}
.correl .onde{display:flex;flex-wrap:wrap;gap:6px}
.correl .onde a{font-size:11px;font-weight:600;color:var(--blue-500);text-decoration:none;background:var(--blue-50);border-radius:6px;padding:3px 9px}
.correl .onde a:hover{background:var(--blue-100)}
.rel-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:11px}
.rel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:13px 15px;cursor:pointer;transition:.2s}
.rel:hover{border-color:var(--blue-300);box-shadow:var(--sh-1)}
.rel .rt{font-family:'Fraunces',serif;font-size:13.5px;color:var(--blue-900);line-height:1.35;margin-top:6px}

footer{border-top:1px solid var(--line);position:relative;z-index:1}
.foot{max-width:1280px;margin:0 auto;padding:22px 28px;display:flex;flex-wrap:wrap;gap:10px;justify-content:space-between;align-items:center;font-size:12px;color:var(--mute)}
.foot b{color:var(--blue-700)}

@media (max-width:1100px){
  .bento{grid-template-columns:repeat(4,1fr)}
  .t-hero{grid-column:span 4}
  .t-wide{grid-column:span 2}
  .panorama{grid-template-columns:200px 1fr;gap:24px}
}
@media (max-width:760px){
  .top{padding:12px 16px}
  .edition{display:none}
  main,.foot{padding-left:16px;padding-right:16px}
  .filters{top:63px}
  #busca{width:150px}
  .panorama{grid-template-columns:1fr;gap:14px;padding-top:20px}
  .radar-wrap{display:none}
  .bento{grid-template-columns:1fr;grid-auto-rows:auto}
  .t-hero,.t-tall,.t-wide{grid-column:span 1;grid-row:span 1;min-height:235px}
  .t-brief{grid-column:span 1}
  .passo{grid-template-columns:1fr;gap:5px}
  .ptag{justify-self:start}
  .nums{padding-left:0}
  .m-body{padding:20px 18px 26px}
  .brand-name{font-size:19px}
}
</style>
</head>
<body>
<div class="atmos"></div><div class="circuit"></div>

<div id="intro">
  <img src="data:image/png;base64,__LOGO__" alt="SeeDs">
  <div class="tag">SEEDS · INTELIGÊNCIA QUE CRESCE</div>
</div>

<header>
  <div class="top">
    <div class="brand">
      <img src="data:image/png;base64,__LOGO__" alt="SeeDs">
      <div>
        <div class="brand-name">See<b>Ds</b> Radar</div>
        <div class="brand-sub">curadoria estratégica</div>
      </div>
    </div>
    <div class="edition"><span class="dot"></span><span id="ed-label"></span></div>
  </div>
</header>

<main>
  <section class="panorama">
    <div class="radar-wrap">
      <div class="radar" id="radar">
        <div class="ring r3"></div><div class="ring r1"></div><div class="ring r2"></div>
        <div class="cross"></div><div class="sweep"></div><div class="core"></div>
      </div>
    </div>
    <div class="pan-info">
      <div class="eyebrow">O radar de hoje</div>
      <h2 class="pan-title">Temas em <em>movimento</em> nesta edição</h2>
      <div class="hot" id="hot"></div>
      <div id="cta-wrap"></div>
    </div>
  </section>

  <nav class="filters">
    <div class="pills" id="pills"></div>
    <input id="busca" type="search" placeholder="Buscar tema, fonte ou palavra…">
    <button id="ptbtn" class="ptbtn" onclick="togglePT()" title="Exibir as notícias em inglês traduzidas para o português"><span class="sw"><span class="knob"></span></span>EN→PT</button>
  </nav>

  <div class="sec-head"><div class="eyebrow" id="grid-titulo">Todas as notícias</div></div>
  <div class="bento" id="grid"></div>
</main>

<footer>
  <div class="foot">
    <div id="foot-legal"><b>SeeDs.AI</b> · Radar gerado e lido localmente na sua máquina · fonte citada em cada matéria</div>
    <div id="prox"></div>
  </div>
</footer>

<div id="overlay"><div id="modal"></div></div>

<script>
const DATA = __DATA__;
const loadedAt = Date.now();
let filtro = DATA.itens.some(i => i.top) ? "top" : "todas", busca = "";
let traduz = localStorage.getItem('seedsPT') !== '0';
let lastModal = null;
const T = it => (traduz && it.pt && it.pt.titulo) ? it.pt.titulo : it.titulo;

/* ---------- intro ---------- */
const intro = document.getElementById('intro');
function fecharIntro(){ if(intro.classList.contains('out')) return;
  intro.classList.add('out'); setTimeout(()=>intro.style.display='none', 950); }
setTimeout(fecharIntro, 2600);
intro.addEventListener('click', fecharIntro);

/* ---------- helpers ---------- */
const esc = s => (s||"").replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const cortar = (s,n) => s.length > n ? s.slice(0,n).replace(/\s\S*$/,"")+"…" : s;
function ago(ts){
  if(!ts) return "";
  const m = Math.max(1, Math.round((Date.now()-ts)/60000));
  if(m < 60) return "há " + m + " min";
  const h = Math.round(m/60);
  if(h < 24) return "há " + h + " h";
  const d = Math.round(h/24);
  return d === 1 ? "ontem" : "há " + d + " dias";
}
function imgErr(el){
  const alt = el.dataset.alt;
  if(alt && !el.dataset.tried){ el.dataset.tried = "1"; el.src = alt; return; }
  const tile = el.closest('.tile'); if(tile) tile.classList.add('semimg');
  const mh = el.closest('.m-head'); if(mh) el.remove();
}
function metaHtml(it, luz){
  return '<div class="meta'+(luz?' luz':'')+'">'+(it.top?'<span class="chip topc">Top</span>':'')+
         '<span class="chip">'+esc(it.catLabel)+'</span>'+
         '<span class="src">'+esc(it.fonte)+'</span><span class="ago">'+ago(it.ts)+'</span></div>';
}

/* ---------- panorama ---------- */
function panorama(){
  const cnt = {};
  DATA.itens.forEach(it => it.temas.forEach(t => cnt[t] = (cnt[t]||0)+1));
  const top = Object.entries(cnt).sort((a,b) => b[1]-a[1]).slice(0,8);
  document.getElementById('hot').innerHTML = top.map(([t,n]) =>
    '<button class="hot-chip" onclick="buscarTema(\''+t.replace(/'/g,"\\'")+'\')"><b>'+esc(t)+'</b><span>'+n+' matérias</span></button>').join("");
  const radar = document.getElementById('radar');
  top.slice(0,6).forEach(([t,n],i) => {
    const ang = (i/6)*Math.PI*2 - Math.PI/2 + .45, r = 26 + (i%3)*10;
    const b = document.createElement('button');
    b.className = 'blip'; b.title = t + ' · ' + n + ' matérias';
    b.style.left = (50 + r*Math.cos(ang)) + '%';
    b.style.top  = (50 + r*Math.sin(ang)) + '%';
    b.onclick = () => buscarTema(t);
    radar.appendChild(b);
  });
}

/* ---------- filtros ---------- */
function itensFiltrados(){
  const q = busca.trim().toLowerCase();
  return DATA.itens.filter(it => {
    if(filtro === "top"){ if(!it.top) return false; }
    else if(filtro !== "todas" && it.cat !== filtro) return false;
    if(!q) return true;
    const extra = it.pt ? " "+it.pt.titulo+" "+it.pt.resumo : "";
    return (it.titulo+" "+it.resumo+extra+" "+it.fonte+" "+it.temas.join(" ")).toLowerCase().includes(q);
  });
}
function renderPills(){
  const el = document.getElementById('pills');
  const counts = {};
  DATA.itens.forEach(it => counts[it.cat] = (counts[it.cat]||0)+1);
  const nTop = DATA.itens.filter(i => i.top).length;
  let h = nTop ? '<button class="pill pill-top'+(filtro==="top"?" on":"")+'" data-c="top">Top News <small>'+nTop+'</small></button>' : '';
  h += '<button class="pill'+(filtro==="todas"?" on":"")+'" data-c="todas">Tudo <small>'+DATA.itens.length+'</small></button>';
  DATA.categorias.forEach(c => {
    h += '<button class="pill'+(filtro===c.id?" on":"")+'" data-c="'+c.id+'">'+esc(c.label)+' <small>'+(counts[c.id]||0)+'</small></button>';
  });
  el.innerHTML = h;
  el.querySelectorAll('.pill').forEach(b => b.onclick = () => { filtro = b.dataset.c; render(); });
}

/* ---------- mosaico ---------- */
const PATTERN = ["hero","tall","brief","brief","brief","wide","wide","brief","brief","brief"];
function tileHtml(it, cls, d){
  const alt = it.imgAlt ? ' data-alt="'+esc(it.imgAlt)+'"' : '';
  return '<article class="tile t-'+cls+'" style="transition-delay:'+(d%8)*55+'ms" onclick="abrir('+it.id+')">'+
    '<img loading="lazy" src="'+esc(it.img)+'"'+alt+' onerror="imgErr(this)" alt="">'+
    '<div class="scrim"></div><div class="tc">'+metaHtml(it, true)+
    '<h3>'+esc(T(it))+'</h3>'+
    (cls==="hero" ? '<p class="tz">'+esc(cortar(it.digest.portras, 160))+'</p>' : '')+
    '</div></article>';
}
function briefHtml(it, d){
  return '<article class="tile t-brief" style="transition-delay:'+(d%8)*55+'ms" onclick="abrir('+it.id+')">'+
    metaHtml(it)+'<h4>'+esc(T(it))+'</h4></article>';
}
const io = new IntersectionObserver(es => es.forEach(e => {
  if(e.isIntersecting){ e.target.classList.add('vis'); io.unobserve(e.target); }
}), {threshold:.1});
function observe(){ document.querySelectorAll('.tile:not(.vis)').forEach(t => io.observe(t)); }

function render(){
  renderPills();
  const lista = itensFiltrados();
  const grid = document.getElementById('grid');
  const labels = Object.fromEntries(DATA.categorias.map(c=>[c.id,c.label]));
  document.getElementById('grid-titulo').textContent =
    (filtro==="top" ? "Top News — o que você precisa saber" : filtro==="todas" ? "Todas as notícias" : labels[filtro])
    + (busca ? ' · "'+busca+'"' : "") + " · " + lista.length;

  if(!lista.length){
    grid.innerHTML = '<div class="vazio">Nada encontrado nessa combinação. Limpe a busca ou troque de categoria.</div>';
    return;
  }
  const imgQ = lista.filter(i => i.img);
  const txtQ = lista.filter(i => !i.img);
  let html = "", slot = 0, d = 0;
  while(imgQ.length || txtQ.length){
    const tipo = PATTERN[slot % PATTERN.length]; slot++;
    let it;
    if(tipo === "brief"){
      it = txtQ.shift() || imgQ.shift();
      if(!it) break;
      html += it.img ? tileHtml(it, "tall", d) : briefHtml(it, d);
    } else {
      it = imgQ.shift();
      if(it) html += tileHtml(it, tipo, d);
      else { it = txtQ.shift(); if(!it) break; html += briefHtml(it, d); }
    }
    d++;
  }
  grid.innerHTML = html;
  observe();
}

/* ---------- modal ---------- */
function abrir(id){
  lastModal = id;
  const it = DATA.itens[id];
  const overlay = document.getElementById('overlay');
  const modal = document.getElementById('modal');
  const dg = it.digest || {};
  const alt = it.imgAlt ? ' data-alt="'+esc(it.imgAlt)+'"' : '';
  const dizTxt = (traduz && it.pt && it.pt.diz) ? it.pt.diz : dg.diz;
  const leituraArr = (traduz && it.pt && it.pt.leitura && it.pt.leitura.length) ? it.pt.leitura : it.leitura;

  const passos = [];
  if(dizTxt) passos.push([DATA.publico ? "Um trecho da matéria" : "A matéria diz", dizTxt]);
  if(dg.portras) passos.push(["Por trás disso", dg.portras]);
  if(dg.conexao) passos.push(["Conexão nesta edição", dg.conexao]);
  const lb2Txt = DATA.publico ? 'SeeDs.AI · leia a reportagem completa na fonte' : 'SeeDs.AI — lida na íntegra, localmente';
  const clara =
    '<div class="clara"><div class="clara-h"><img src="data:image/png;base64,__CLARA__" alt="Clara">'+
    '<div><div class="lb">Clara · Leitura estratégica</div><div class="lb2">'+lb2Txt+'</div></div></div>'+
    passos.map(p => '<div class="passo"><span class="ptag">'+p[0]+'</span><p>'+esc(p[1])+'</p></div>').join("")+
    (dg.numeros && dg.numeros.length ? '<div class="nums">'+dg.numeros.map(n=>'<span>'+esc(n)+'</span>').join("")+'</div>' : '')+
    '</div>';

  const leitura = leituraArr && leituraArr.length ?
    '<details class="leitura"'+(it.top?' open':'')+'><summary>Essência da matéria — leia aqui mesmo <small>('+leituraArr.length+' parágrafos · útil quando a fonte pede assinatura)</small></summary>'+
    '<div class="lp">'+leituraArr.map(p=>'<p>'+esc(p)+'</p>').join("")+'</div></details>' : '';

  const temas = it.temas.map(t => '<span class="tema-chip" onclick="buscarTema(\''+esc(t).replace(/'/g,"\\'")+'\')">'+esc(t)+'</span>').join("");
  const correl = it.correl.map(c =>
    '<div class="correl"><div class="t">'+esc(c.tema)+'</div><div class="e">'+esc(c.efeito)+'</div>'+
    '<div class="onde">'+c.onde.map(o=>'<a href="'+esc(o.url)+'" target="_blank" rel="noopener">'+esc(o.nome)+' ↗</a>').join("")+'</div></div>').join("");
  const rel = it.rel.map(j => { const r = DATA.itens[j];
    return '<div class="rel" onclick="abrir('+r.id+')">'+metaHtml(r)+'<div class="rt">'+esc(T(r))+'</div></div>'; }).join("");

  modal.innerHTML =
    '<div class="m-head">'+(it.img?'<img src="'+esc(it.img)+'"'+alt+' onerror="imgErr(this)" alt="">':'')+
      '<button class="m-close" onclick="fechar()">✕</button></div>'+
    '<div class="m-body">'+
      metaHtml(it)+
      '<h2>'+esc(T(it))+'</h2>'+
      '<div><a class="fonte-link" href="'+esc(it.link)+'" target="_blank" rel="noopener">Ler na fonte · '+esc(it.fonte)+' ↗</a>'+
      (it.lang==='en' && traduz && it.pt ? '<span class="trad-note">tradução automática do inglês</span>' : '')+'</div>'+
      clara + leitura +
      (temas?'<div class="temas">'+temas+'</div>':'')+
      (correl?'<div class="sec-t">Radar de correlações — o que observar a partir daqui</div><div class="correl-grid">'+correl+'</div>':'')+
      (rel?'<div class="sec-t" id="conexoes">Conexões nesta edição</div><div class="rel-grid">'+rel+'</div>':'')+
    '</div>';
  overlay.classList.add('show');
  overlay.scrollTop = 0;
  document.body.style.overflow = 'hidden';
}
function fechar(){
  document.getElementById('overlay').classList.remove('show');
  document.body.style.overflow = '';
}
function buscarTema(t){
  fechar(); filtro = "todas";
  document.getElementById('busca').value = t;
  busca = t; render();
  window.scrollTo({top:0, behavior:'smooth'});
}
function togglePT(){
  traduz = !traduz;
  localStorage.setItem('seedsPT', traduz ? '1' : '0');
  syncPT(); render();
  if(document.getElementById('overlay').classList.contains('show') && lastModal !== null) abrir(lastModal);
}
function syncPT(){ document.getElementById('ptbtn').classList.toggle('on', traduz); }
document.getElementById('overlay').addEventListener('click', e => { if(e.target.id==='overlay') fechar(); });
document.addEventListener('keydown', e => { if(e.key==='Escape') fechar(); });
document.getElementById('busca').addEventListener('input', e => { busca = e.target.value; render(); });

/* ---------- edição / auto-atualização ---------- */
document.getElementById('ed-label').textContent = 'Edição de ' + DATA.geradoLabel;
function prox(){
  const alvo = DATA.geradoTs + DATA.intervaloHoras*3600*1000;
  const falta = alvo - Date.now();
  const el = document.getElementById('prox');
  if(falta <= 0){ el.textContent = 'Nova edição a caminho — a página recarrega sozinha.'; return; }
  const h = Math.floor(falta/3600000), m = Math.round((falta%3600000)/60000);
  el.textContent = 'Próxima edição automática em ~' + (h>0 ? h+'h'+String(m).padStart(2,'0') : m+' min');
}
prox(); setInterval(prox, 60000);
setTimeout(() => location.reload(), 30*60*1000);
document.addEventListener('visibilitychange', () => {
  if(!document.hidden && Date.now()-loadedAt > 20*60*1000) location.reload();
});

if(DATA.publico){
  document.getElementById('foot-legal').innerHTML =
    '<b>SeeDs.AI</b> · Curadoria e interpretação SeeDs.AI · os direitos das matérias pertencem às fontes citadas';
  if(DATA.ctaUrl){
    document.getElementById('cta-wrap').innerHTML =
      '<a class="assine-btn" href="'+esc(DATA.ctaUrl)+'" target="_blank" rel="noopener">Assine o Radar — receba as próximas edições →</a>';
  }
}

syncPT();
panorama();
render();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------- main

if __name__ == "__main__":
    usar_ai = "--ai" in sys.argv
    publico = "--publico" in sys.argv
    if "--loop" in sys.argv:
        while True:
            try:
                gerar_edicao(usar_ai, publico)
            except Exception as exc:
                print(f"[erro] {type(exc).__name__}: {exc}")
            print(f"Próxima atualização em {INTERVALO_HORAS} horas…")
            time.sleep(INTERVALO_HORAS * 3600)
    else:
        gerar_edicao(usar_ai, publico)
