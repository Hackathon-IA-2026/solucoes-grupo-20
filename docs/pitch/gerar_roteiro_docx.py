#!/usr/bin/env python3
"""Gera docs/pitch/roteiro_pitch.docx a partir do roteiro do pitch de 5 minutos."""
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

PREDICTA = RGBColor(0x4F, 0x46, 0xE5)
LARANJA = RGBColor(0xDC, 0x6B, 0x18)
CINZA = RGBColor(0x64, 0x74, 0x8B)

SECOES = [
    (
        "Slide 1 · Problema", "0:00 – 0:40",
        [
            "Consumo e demanda não são sinônimos. Consumo é a energia acumulada em kWh; demanda é a potência exigida em cada instante. "
            "Dois clientes podem consumir o mesmo no mês e produzir impactos muito diferentes na rede se um deles concentrar o uso em poucas horas.",
            "E essa curva não depende apenas de calor. Temperatura, umidade, nebulosidade, calendário, hábitos locais e geração distribuída podem coincidir e amplificar rampas ou picos de forma diferente em cada região.",
            "Hoje a tarifa plana não mostra ao consumidor quando deslocar sua carga flexível. A oportunidade é antecipar a forma da curva, não apenas o volume total.",
        ],
    ),
    (
        "Slide 2 · Solução: os dois motores", "0:40 – 1:45",
        [
            "Este é o núcleo da solução. Entram carga, geração e DESSEM do ONS, tarifas da ANEEL, ativos geoespaciais e previsão meteorológica.",
            "O clima não entra como valor isolado. Temperatura, chuva, vento e radiação são comparados a uma referência mensal de dez anos por subsistema. Anomalias e eventos persistentes ajudam o XGBoost a reconhecer quando o contexto local pode alterar a curva.",
            "O Motor 1 gera vinte e quatro previsões diretas, de H01 a H24, com P10, P50 e P90. Só publica com carga recente, clima completo, horas sem duplicidade e intervalos coerentes.",
            "O contrato auditável leva previsão, drivers, origem e qualidade ao Motor 2. A tarifa fica entre 85% e 130% da base, varia no máximo 10% por hora, mantém neutralidade com tolerância de 1%, limita a fatura a mais 20% e volta a 1,0 se o dado falhar.",
        ],
    ),
    (
        "Slide 3 · Demo ao vivo", "1:45 – 2:25",
        [
            "Deixa eu mostrar isso funcionando. [ABRIR /produto/]",
            "No mapa real da ANEEL, escolho a [DISTRIBUIDORA], um perfil tarifário e uma janela histórica. [SIMULAR]",
            "Aqui estão as três curvas na mesma hora: programação DESSEM, previsão Predicta e carga realizada. Abaixo, o cliente vê o sinal horário e a economia potencial.",
            "Na visão da distribuidora, ajusto a adesão da carteira e mostro quanto o pico cai em MW, preservando a energia total do dia.",
        ],
    ),
    (
        "Slide 4 · Precisão contra DESSEM", "2:25 – 3:10",
        [
            "A comparação usa uma régua única. Selecionamos as 672 horas em que existem Predicta, DESSEM e carga realizada. Para cada previsão, somamos o erro absoluto horário e dividimos pela carga realizada total. Esse é o WAPE: quanto menor, melhor.",
            "A Predicta teve 12,5% menos erro no Norte, 47,7% no Nordeste, 19,2% no Sul e 36,4% no Sudeste/Centro-Oeste em relação ao DESSEM.",
            "Esses percentuais são redução relativa do erro, não diferença de carga. Por exemplo: no Sudeste/Centro-Oeste, o WAPE caiu de 3,62% no DESSEM para 2,30% na Predicta.",
            "A ressalva metodológica é clara: usamos a programação DESSEM publicada, mas o arquivo foi obtido retrospectivamente. A comparação histórica é válida; o próximo passo é arquivar cada emissão em tempo real para um teste operacional auditável.",
        ],
    ),
    (
        "Slide 5 · Modelo de negócio", "3:10 – 3:50",
        [
            "A distribuidora paga implantação e serviço recorrente. Em troca, ganha uma ferramenta para deslocar carga, reduzir coincidência de pico e testar capacidade evitada antes de investir na expansão da rede.",
            "O consumidor recebe a previsão de 24 horas pela distribuidora e escolhe aderir. Serviços de horizonte estendido e otimização automática podem formar uma camada premium.",
            "O valor é compartilhado: menor pico para a distribuidora, decisão simples para o consumidor e menos pressão nas horas críticas para o sistema.",
        ],
    ),
    (
        "Slide 6 · Viabilidade e roadmap", "3:50 – 4:25",
        [
            "Isso não é um mockup: o pipeline roda de ponta a ponta, cobre os quatro subsistemas com histórico de 2023 a 2026 e expõe uma API para integração ao faturamento.",
            "Ainda precisamos operar a previsão meteorológica ao vivo e automatizar a execução contínua 24 por 7.",
            "O caminho natural é um piloto com uma distribuidora em ambiente regulatório experimental: "
            "primeiro em modo sombra, com a tarifa simulada rodando em paralelo à real; depois opt-in com clientes voluntários; depois escala.",
        ],
    ),
    (
        "Slide 7 · Inovação", "4:25 – 4:50",
        [
            "Bandeiras e tarifa branca são estáticas ou reativas. A Predicta é preditiva, horária, regional e protegida por limites automáticos.",
            "Como os motores são desacoplados, a distribuidora integra o sinal ao sistema existente sem reconstruir toda a operação.",
        ],
    ),
    (
        "Slide 8 · Fechamento", "4:50 – 5:00",
        [
            "A curva de carga responde ao clima, ao calendário e ao comportamento. A tarifa precisa aprender a acompanhar.",
            "Somos a Predicta — e buscamos uma distribuidora parceira para o piloto. Obrigada.",
        ],
    ),
]

OBSERVACOES = [
    "Placeholders [R$ X], [Y], [Z], [N] e [DISTRIBUIDORA]: preencher com os valores do cenário de demo congelado "
    "(ensaiar a simulação e anotar os números exibidos na tela).",
    "Validação citada: 672 horas comuns entre Predicta, DESSEM e realizado. Ganho relativo: N 12,5%; NE 47,7%; S 19,2%; SE/CO 36,4%.",
    "Modelo apresentado: XGBoost com clima contextualizado por referência mensal de 10 anos, anomalias, percentis e eventos persistentes.",
    "Ritmo alvo: 125–135 palavras/minuto. Ensaiar 3× com cronômetro; a demo de 40s é o maior risco — ter screenshot de backup nos slides.",
    "Se a demo falhar: seguir com o screenshot do slide 3 e citar os números memorizados sem quebrar a narrativa.",
]


def main() -> None:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    titulo = doc.add_paragraph()
    titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = titulo.add_run("Predicta · Roteiro do Pitch — 5 minutos")
    run.bold = True
    run.font.size = Pt(20)
    run.font.color.rgb = PREDICTA

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = sub.add_run("Demanda energética, clima e operação do sistema · Hackathon 2026")
    run.font.color.rgb = CINZA
    run.font.size = Pt(11)

    for nome, tempo, falas in SECOES:
        h = doc.add_paragraph()
        h.space_before = Pt(14)
        run = h.add_run(f"{nome}  ")
        run.bold = True
        run.font.size = Pt(14)
        run.font.color.rgb = PREDICTA
        run = h.add_run(f"[{tempo}]")
        run.bold = True
        run.font.size = Pt(11)
        run.font.color.rgb = LARANJA
        for fala in falas:
            p = doc.add_paragraph(fala)
            p.paragraph_format.space_after = Pt(6)

    h = doc.add_paragraph()
    run = h.add_run("Observações de preparação")
    run.bold = True
    run.font.size = Pt(14)
    run.font.color.rgb = PREDICTA
    for obs in OBSERVACOES:
        doc.add_paragraph(obs, style="List Bullet")

    out = Path(__file__).with_name("roteiro_pitch.docx")
    doc.save(out)
    print(f"OK: {out}")


if __name__ == "__main__":
    main()
