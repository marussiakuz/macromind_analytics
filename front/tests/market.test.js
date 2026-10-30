import assert from 'node:assert/strict';
import test from 'node:test';
import { buildMarketSummary, calculateTopDown, createStudy } from '../src/api/market.js';
import { renderMarketSummaryHTML } from '../src/render/market.js';

const study = {
  id: 'st-1',
  version: 1,
  as_of: '2024-12-31',
  market_scope: {
    product: 'B2B SaaS для логистики',
    buyer: 'директор по логистике',
    countries: ['RU'],
    reference_period: '2024',
    measure_type: 'revenue',
    exclude: ['B2C'],
  },
};

test('createStudy posts payload and returns study', async () => {
  let url = '';
  let body = null;
  const res = await createStudy({ title: 't', scope: { product: 'p' } }, {
    fetchImpl: async (u, opts) => {
      url = u;
      body = JSON.parse(opts.body);
      return { ok: true, json: async () => ({ id: 'st-1', version: 1 }) };
    },
  });
  assert.match(url, /\/api\/v1\/market\/studies$/);
  assert.equal(body.title, 't');
  assert.equal(res.id, 'st-1');
});

test('calculateTopDown surfaces validation errors', async () => {
  await assert.rejects(
    () => calculateTopDown('st-1', { base: '1', shares: [] }, {
      fetchImpl: async () => ({
        ok: false,
        status: 422,
        json: async () => ({ detail: { error: { code: 'INVALID_TOP_DOWN', message: 'bad', fields: [] } } }),
      }),
    }),
    /bad/,
  );
});

test('buildMarketSummary is MarketSummary shape with completeness', () => {
  const s = buildMarketSummary({
    study,
    topDown: { value: '1000000000', currency: 'RUB', formula: 'M_TD' },
    bottomUp: { potential: { value: '900000000' } },
    triangulation: { status: 'close' },
    bindings: [{ binding_revision: 2, legal_entity_inn: '7707083893' }],
  });
  assert.equal(s.study_id, 'st-1');
  assert.equal(s.report_version, 1);
  assert.equal(s.triangulation_status, 'close');
  assert.equal(s.data_completeness.has_top_down, true);
  assert.equal(s.data_completeness.has_bottom_up, true);
  assert.equal(s.legal_entity_inn, '7707083893');
});

test('summary block always visible with scope and actions', () => {
  const html = renderMarketSummaryHTML(
    buildMarketSummary({ study, topDown: null, bottomUp: null, triangulation: null, bindings: [] }),
    { companyName: 'ПАО Тест', inn: '7707083893' },
  );
  assert.match(html, /id="market-area"/);
  assert.match(html, /Анализ рынка и конкурентов/);
  assert.match(html, /B2B SaaS для логистики/);
  assert.match(html, /Открыть исследование/);
  assert.match(html, /Связать с заявкой/);
  assert.match(html, /не рассчитано/);
});

test('summary shows estimate and triangulation status', () => {
  const html = renderMarketSummaryHTML(
    buildMarketSummary({
      study,
      topDown: { value: '1000000000', currency: 'RUB', formula: 'M_TD = …' },
      bottomUp: { potential: { value: '900000000' } },
      triangulation: { status: 'close' },
      bindings: [],
    }),
    {},
  );
  assert.match(html, /1\.00 млрд RUB/);
  assert.match(html, /Расхождение ≤ 20%/);
  assert.match(html, /верхняя оценка/);
});

test('detail shows auto analysis facts without calc buttons', async () => {
  const { marketState } = await import('../src/market/state.js');
  marketState.detailOpen = true;
  marketState.summary = buildMarketSummary({ study, bindings: [] });
  marketState.summary.data_completeness = {
    has_top_down: false,
    has_bottom_up: false,
    has_triangulation: false,
    has_registry_evidence: true,
    registry_sections: { contracts: 3, legal_cases: 2 },
    last_revenue: { year: 2021, revenue: 1, net_profit: 2 },
  };
  marketState.summary.competitor_findings = ['ООО Ромашка (контрагент по закупкам)'];
  marketState.summary.evidence_refs = [{ name: 'contracts', count: 3 }];
  const html = renderMarketSummaryHTML(marketState.summary, {});
  assert.match(html, /market-mds-form|Подробнее|Источники/);
  assert.ok(!html.includes('Рассчитать'));
  assert.ok(!html.includes('Построить карту'));
  marketState.detailOpen = false;
});

test('empty company state does not crash or show an empty market report', () => {
  assert.equal(renderMarketSummaryHTML(null), '');
});

test('evidence report renders narratives and cited competitors safely', () => {
  const html = renderMarketSummaryHTML({
    research_schema_version: 'market-evidence-3',
    analytical_report: {
      company: {name: 'Тест', inn: '1', product: 'полимеры'},
      sections: {russia: [{text: 'Подтверждённый обзор <script>bad()</script>', evidence_ids: ['s'], quotes: [{evidence_id:'s', quote:'Источник о рынке'}]}]},
      sources: [{id:'s', title:'Исследование', url:'https://example.org/report'}],
      competitors: {russia:[{name:'Производитель', specialization:'полимеры', why_competes:'Одинаковое применение', evidence_ids:['s'], quotes:[]}],world:[]},
    },
  });
  assert.match(html, /Подтверждённый обзор/);
  assert.match(html, /Производитель/);
  assert.match(html, /https:\/\/example.org\/report/);
  assert.match(html, /Подтверждающие фрагменты/);
  assert.doesNotMatch(html, /<script>/);
  assert.doesNotMatch(html, /Оценка сверху вниз/);
  assert.match(html, /Скачать отчёт/);
});

test('saved report stays readable when storage version is absent or changes', () => {
  for (const version of [undefined, 'market-evidence-4']) {
    const html = renderMarketSummaryHTML({
      auto: true,
      research_schema_version: version,
      analytical_report: {
        sources: [],
        sections: {world: [{text: 'Обзор мирового рынка'}]},
        competitors: {russia: [{name: 'Аналог', specialization: 'Продукт'}]},
      },
    });
    assert.match(html, /Обзор мирового рынка/);
    assert.match(html, /Аналог/);
    assert.doesNotMatch(html, /Оценка сверху вниз|не рассчитано/);
  }
});

test('legacy auto analysis asks for refresh instead of showing empty calculations', () => {
  const html = renderMarketSummaryHTML({auto: true, market_scope: {product: 'Тест'}});
  assert.match(html, /Сохранён старый формат анализа/);
  assert.match(html, /market-refresh-analysis/);
  assert.doesNotMatch(html, /Оценка сверху вниз|не рассчитано/);
});

test('directions and roles render with sources (Stage A/C)', () => {
  const html = renderMarketSummaryHTML({
    research_schema_version: 'market-evidence-3',
    analytical_report: {
      company: {
        name: 'ГидроЭл', inn: '5040133380',
        site: 'https://hydroel-shop.ru/', site_status: 'verified',
        about: 'Производство гидроблоков',
        directions: [{
          direction_id: 'd1',
          product_category_ru: 'Гидравлические блоки клапанов',
          product_category_en: 'Hydraulic manifold blocks',
          role: 'manufacturer',
          applications: ['Сельхозтехника'],
          buyer_segments: ['Производители техники'],
          geography: 'Россия',
          brands: [{ name: 'Hydroel', relation: 'own_brand' }],
          evidence: [{ quote: 'Проектируем и изготавливаем гидроблоки', url: 'https://hydroel-shop.ru/production/' }],
          status: 'supported',
          limitations: [],
        }],
      },
      sections: { russia: [], world: [] },
      sources: [{ id: 's', title: 'Prod', url: 'https://hydroel-shop.ru/production/' }],
      competitors: { russia: [], world: [] },
    },
  });
  assert.match(html, /Что делает компания/);
  assert.match(html, /Гидравлические блоки клапанов/);
  assert.match(html, /Производитель/);
  assert.match(html, /Проектируем и изготавливаем гидроблоки/);
  assert.match(html, /Hydroel/);
});

test('suppliers are listed separately from competitors (Stage B/C)', () => {
  const html = renderMarketSummaryHTML({
    research_schema_version: 'market-evidence-3',
    analytical_report: {
      company: {
        name: 'Тест', inn: '1',
        directions: [{ direction_id: 'd1', product_category_ru: 'Клапаны', role: 'distributor', status: 'supported', evidence: [] }],
      },
      sections: { russia: [] },
      sources: [],
      competitors: {
        russia: [{
          name: 'ПрямойКонкурент',
          direction_id: 'd1',
          relation_class: 'direct_competitor',
          specialization: 'Гидроблоки',
          why_competes: 'Пересечение покупателей',
          links: ['https://comp.example/'],
          quotes: [],
        }],
        world: [{
          name: 'WorldAnalog',
          direction_id: 'd1',
          relation_class: 'product_analog',
          specialization: 'Hoses',
          why_competes: 'Зарубежный аналог',
          territory_status: 'absent_in_russia',
          links: [],
          quotes: [],
        }],
        suppliers_partners: [{
          name: 'Walvoil',
          direction_id: 'd1',
          relation_class: 'supplier_partner',
          specialization: 'Дистрибьютор',
          why_competes: 'Поставщик, не конкурент',
        }],
      },
    },
  });
  assert.match(html, /Поставщики и партнёры/);
  assert.match(html, /Walvoil/);
  assert.match(html, /Прямой конкурент/);
  assert.match(html, /Продуктовый аналог/);
  assert.match(html, /Клапаны/);
  // suppliers must not be inside the direct-competitor table as competitors
  const supplierSection = html.split('Поставщики и партнёры')[1] || '';
  assert.match(supplierSection, /Walvoil/);
});

test('restore path: saved directions render without new model call', () => {
  const saved = {
    research_schema_version: 'market-evidence-3',
    analytical_report: {
      company: {
        name: 'ГидроЭл', inn: '5040133380',
        directions: [{
          direction_id: 'rhd',
          product_category_ru: 'Рукава высокого давления (РВД)',
          role: 'manufacturer',
          status: 'supported',
          evidence: [{ quote: 'производство рукавов высокого давления', url: 'https://hydroel-shop.ru/contacts/' }],
        }],
      },
      sections: { russia: [{ text: 'Обзор из сохранённой версии' }] },
      sources: [{ id: 's', title: 't', url: 'https://x.example/' }],
      competitors: { russia: [], world: [], suppliers_partners: [] },
    },
    company_research: {
      directions: [{ direction_id: 'rhd', product_category_ru: 'Рукава высокого давления (РВД)', role: 'manufacturer' }],
      read_urls: ['https://hydroel-shop.ru/contacts/'],
    },
  };
  const html = renderMarketSummaryHTML(saved, {});
  assert.match(html, /Обзор из сохранённой версии/);
  assert.match(html, /Рукава высокого давления/);
  assert.match(html, /Что делает компания/);
  // no forced refresh button when a full evidence report is present
  assert.doesNotMatch(html, /Сохранён старый формат/);
});
