"""Regression: own-site discoveries must not replace sourced competitor descriptions."""
import json
from types import SimpleNamespace

import pytest
from osint_agent.market.analytical_report import finalize_competitors
from osint_agent.market.site_research import infer_company_directions


def test_resolves_citations_and_removes_investigated_company_links():
    sources = [
        {'id':'own', 'url':'https://company.example/products', 'quote':'Платформа Альфа — наш продукт.'},
        {'id':'other', 'url':'https://vendor.example/products', 'title':'Vendor products',
         'quote':'Компания Бета разрабатывает распознавание автомобильных номеров.'},
    ]
    row = {'name':'Бета','specialization':'Распознавание автомобильных номеров',
           'why_competes':'Совпадает задача контроля въезда транспорта',
           'evidence_ids':['own','other'], 'quotes':[
               {'evidence_id':'own','quote':sources[0]['quote']},
               {'evidence_id':'other','quote':sources[1]['quote']}]}
    result = finalize_competitors({'russia':[row]}, sources,
                                 {'company_research':{'official_site':'https://company.example'}})
    actual = result['russia'][0]
    assert actual['links'] == ['https://vendor.example/products']
    assert actual['evidence_ids'] == ['other']
    assert actual['quotes'][0]['url'] == actual['links'][0]
    assert actual['specialization'] != actual['why_competes']


def test_rejects_own_site_only_boilerplate_and_fabricated_quote():
    source={'id':'s','url':'https://own.example','quote':'Наши системы распознавания'}
    row={'name':'Кандидат','specialization':'Продукт','why_competes':'Применение',
         'quotes':[{'evidence_id':'s','quote':source['quote']}]}
    own={'company_research':{'read_urls':['https://own.example/products']}}
    assert not finalize_competitors({'russia':[row]},[source],own)['russia']
    assert not finalize_competitors({'russia':[{**row,'why_competes':'Продукт'}]},[source],{})['russia']
    row['quotes'][0]['quote']='Выдуманное описание продукции'
    assert not finalize_competitors({'russia':[row]},[source],{})['russia']


@pytest.mark.asyncio
async def test_direction_quotes_are_specific_verbatim_and_not_generic_paragraphs():
    text='Компания разрабатывает распознавание номеров автомобилей. Компания оказывает услуги исследования изображений и технического консультирования.'
    class LLM:
        async def complete(self, system, payload, **kwargs):
            pid=payload['sources'][0]['id']
            rows=[]
            for i,quote in enumerate(['разрабатывает распознавание номеров автомобилей',
                                      'оказывает услуги исследования изображений',
                                      'Несуществующий завод производит камеры наблюдения']):
                rows.append({'direction_id':f'd{i}', 'product_category_ru':f'Направление {i}',
                    'description':f'Описание направления {i}', 'role':'service_provider',
                    'status':'supported', 'evidence_ids':[pid],
                    'evidence_claims':[{'evidence_id':pid,'quote':quote}]})
            return SimpleNamespace(ok=True,text=json.dumps({'directions':rows}),error=None)
    result=await infer_company_directions({'name':'Тест'},[{'url':'https://own.example','text':text}],LLM())
    first,second,unsupported=result['directions']
    assert first['evidence'][0]['quote'] != second['evidence'][0]['quote']
    assert first['evidence'][0]['quote'] in text
    assert len(first['evidence'][0]['quote']) < len(text)
    assert unsupported['status']=='unresolved'
    assert not unsupported['description']
    assert not unsupported['evidence']


def test_saved_report_is_sanitized_without_new_model_call():
    from osint_agent.api.market import _sanitize_analysis_payload
    summary={'legal_entity_inn':'1','external_evidence':[
        {'id':'s','url':'https://vendor.example','quote':'Бета выпускает насосы.'}],
        'analytical_report':{'sections':{},'company':{},'competitors':{'russia':[
            {'name':'Бета','specialization':'Насосы','why_competes':'Для перекачки жидкостей',
             'quotes':[{'evidence_id':'s','quote':'Бета выпускает насосы.'}]},
            {'name':'Награда компании','specialization':'Сопоставимая продукция',
             'why_competes':'Сопоставимая продукция','quotes':[]}]}}}
    result=_sanitize_analysis_payload(summary)
    assert [r['name'] for r in result['analytical_report']['competitors']['russia']]==['Бета']
    assert 'https://vendor.example' in result['report_html']
    assert 'Награда компании' not in result['report_html']
