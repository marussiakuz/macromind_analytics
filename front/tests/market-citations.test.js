import assert from 'node:assert/strict';
import test from 'node:test';
import { renderAnalyticalReportHTML } from '../src/render/market.js';

test('direction shared evidence appears once and concrete descriptions remain distinct', () => {
  const evidence = [{url:'https://company.example',quote:'Общая цитата со страницы компании'}];
  const html = renderAnalyticalReportHTML({sections:{},company:{directions:[
    {direction_id:'d1',product_category_ru:'Распознавание',description:'Создаёт программу распознавания номеров',evidence},
    {direction_id:'d2',product_category_ru:'Консалтинг',description:'Исследует методы обработки изображений',evidence},
  ]}});
  assert.equal(html.split('Общая цитата со страницы компании').length-1,1);
  assert.match(html,/Общие источники направлений/);
  assert.match(html,/Создаёт программу распознавания номеров/);
  assert.match(html,/Исследует методы обработки изображений/);
});

test('competitor with ID-only citations has source links and non-duplicated description', () => {
  const html = renderAnalyticalReportHTML({sections:{},company:{directions:[]},
    sources:[{id:'s',url:'https://vendor.example/product',title:'Продукты конкурента'}],
    competitors:{russia:[{name:'Бета', specialization:'Разрабатывает системы анализа изображений',
      why_competes:'Решает ту же задачу контроля качества',evidence_ids:['s'],
      quotes:[{evidence_id:'s',quote:'Система Бета проверяет дефекты изделий'}]}]}});
  assert.match(html,/href="https:\/\/vendor.example\/product"/);
  assert.equal(html.split('Разрабатывает системы анализа изображений').length-1,1);
  assert.equal(html.split('Решает ту же задачу контроля качества').length-1,1);
  assert.match(html,/Подтверждающие фрагменты/);
});
