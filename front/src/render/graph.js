/**
 * Graph Visualization — визуализация графа связей компании через vis-network.
 *
 * Используется в проекте для отображения связей между компанией,
 * людьми, доменами, IP-адресами и email.
 */

import { Network } from 'vis-network';
import { DataSet } from 'vis-data';

// Цвета для типов узлов (соответствуют NODE_TYPES из бэкенда)
const NODE_COLORS = {
  person: { color: '#FF6B6B', shape: 'dot', icon: '👤' },
  company: { color: '#4ECDC4', shape: 'dot', icon: '🏢' },
  domain: { color: '#45B7D1', shape: 'dot', icon: '🌐' },
  ip: { color: '#96CEB4', shape: 'dot', icon: '🖥️' },
  email: { color: '#FFEAA7', shape: 'dot', icon: '📧' },
  phone: { color: '#DDA0DD', shape: 'dot', icon: '📱' },
  organization: { color: '#A8E6CF', shape: 'dot', icon: '🏫' },
};

// Цвета для типов связей
const EDGE_COLORS = {
  works_at: '#666666',
  owns: '#FF6B6B',
  hosted_on: '#45B7D1',
  sends_email: '#FFEAA7',
  friend_of: '#A8E6CF',
  studied_at: '#DDA0DD',
  related_to: '#999999',
};

let networkInstance = null;

/**
 * Создать и отрисовать граф в контейнере.
 *
 * @param {HTMLElement} container — DOM-элемент для графа
 * @param {Object} graphData — { nodes: [...], edges: [...] } из API
 * @param {Object} options — дополнительные настройки
 * @returns {Network} экземпляр vis-network
 */
export function renderGraph(container, graphData, options = {}) {
  // Prepare nodes with styling
  const nodes = new DataSet(
    graphData.nodes.map((node) => {
      const style = NODE_COLORS[node.type] || NODE_COLORS.organization;
      return {
        id: node.id,
        label: node.label,
        group: node.type,
        title: node.title || node.label,
        color: {
          background: style.color,
          border: style.color,
          highlight: { background: style.color, border: '#ffffff' },
        },
        font: { color: '#ffffff', size: 14 },
        shape: style.shape,
        size: options.nodeSize || 25,
      };
    })
  );

  // Prepare edges with styling
  const edges = new DataSet(
    graphData.edges.map((edge) => ({
      id: edge.id || `${edge.from}-${edge.to}`,
      from: edge.from,
      to: edge.to,
      label: edge.label || '',
      arrows: edge.arrows || 'to',
      color: {
        color: EDGE_COLORS[edge.type] || '#666666',
        highlight: '#ffffff',
      },
      font: { color: '#999999', size: 10, strokeWidth: 0 },
      smooth: { type: 'continuous' },
    }))
  );

  // Network options
  const networkOptions = {
    nodes: {
      borderWidth: 2,
      shadow: true,
    },
    edges: {
      width: 2,
      shadow: true,
      smooth: {
        type: 'continuous',
        roundness: 0.5,
      },
    },
    physics: {
      enabled: true,
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {
        gravitationalConstant: -50,
        centralGravity: 0.01,
        springLength: 150,
        springConstant: 0.08,
        damping: 0.4,
      },
      stabilization: {
        iterations: 100,
        updateInterval: 25,
      },
    },
    interaction: {
      hover: true,
      tooltipDelay: 200,
      zoomView: true,
      dragView: true,
    },
    ...options,
  };

  // Destroy previous instance
  if (networkInstance) {
    networkInstance.destroy();
  }

  // Create network
  networkInstance = new Network(container, { nodes, edges }, networkOptions);

  // Stabilization complete event
  networkInstance.once('stabilizationIterationsDone', () => {
    networkInstance.setOptions({ physics: { enabled: false } });
  });

  return networkInstance;
}

/**
 * Получить текущий экземпляр Network.
 */
export function getNetwork() {
  return networkInstance;
}

/**
 * Уничтожить граф.
 */
export function destroyGraph() {
  if (networkInstance) {
    networkInstance.destroy();
    networkInstance = null;
  }
}

/**
 * Включить/выключить физику.
 */
export function togglePhysics(enabled) {
  if (networkInstance) {
    networkInstance.setOptions({ physics: { enabled } });
  }
}

/**
 * Подогнать граф под экран.
 */
export function fitGraph() {
  if (networkInstance) {
    networkInstance.fit({ animation: true });
  }
}

/**
 * Фильтровать узлы по типу.
 *
 * @param {Network} network
 * @param {string[]} visibleTypes — типы узлов для отображения
 * @param {Object} graphData — исходные данные графа
 */
export function filterByType(network, visibleTypes, graphData) {
  const filteredNodes = graphData.nodes.filter((n) => visibleTypes.includes(n.type));
  const visibleIds = new Set(filteredNodes.map((n) => n.id));
  const filteredEdges = graphData.edges.filter(
    (e) => visibleIds.has(e.from) && visibleIds.has(e.to)
  );

  const nodes = network.body.data.nodes;
  const edges = network.body.data.edges;

  nodes.clear();
  nodes.add(
    filteredNodes.map((node) => {
      const style = NODE_COLORS[node.type] || NODE_COLORS.organization;
      return {
        id: node.id,
        label: node.label,
        group: node.type,
        title: node.title || node.label,
        color: {
          background: style.color,
          border: style.color,
        },
        font: { color: '#ffffff', size: 14 },
        shape: style.shape,
        size: 25,
      };
    })
  );

  edges.clear();
  edges.add(
    filteredEdges.map((edge) => ({
      id: edge.id || `${edge.from}-${edge.to}`,
      from: edge.from,
      to: edge.to,
      label: edge.label || '',
      arrows: edge.arrows || 'to',
      color: { color: EDGE_COLORS[edge.type] || '#666666' },
      font: { color: '#999999', size: 10, strokeWidth: 0 },
    }))
  );
}

/**
 * Сгенерировать HTML для панели фильтров.
 */
export function renderFiltersHTML(graphData) {
  const typeCounts = {};
  graphData.nodes.forEach((n) => {
    typeCounts[n.type] = (typeCounts[n.type] || 0) + 1;
  });

  return Object.entries(typeCounts)
    .map(([type, count]) => {
      const style = NODE_COLORS[type] || NODE_COLORS.organization;
      return `
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked data-filter-type="${type}" class="graph-filter-checkbox rounded">
          <span class="text-sm">${style.icon} ${type} (${count})</span>
        </label>
      `;
    })
    .join('');
}

/**
 * Сгенерировать HTML для статистики графа.
 */
export function renderStatsHTML(stats) {
  return `
    <div class="flex items-center gap-4 text-sm text-text-secondary">
      <span>Узлов: <strong class="text-text-main">${stats.nodes}</strong></span>
      <span>Связей: <strong class="text-text-main">${stats.edges}</strong></span>
    </div>
  `;
}
