export const mockProjects = [
  {
    id: 'proj-001',
    name: 'BioTech Solutions',
    inn: '7701234567',
    status: 'На анализе',
    stage: 'DD',
    documentsUploaded: 7,
    documentsRequired: 12,
    progress: 58,
    submittedAt: '2026-03-01',
    assignedAnalyst: 'Иван Петров',
    description: 'Биотехнологическая платформа для персонализированной медицины',
    industry: 'Biotech',
    stage_funding: 'Seed',
    team_size: 8,
  },
  {
    id: 'proj-002',
    name: 'FinTech Pro',
    inn: '7702345678',
    status: 'Заявка принята',
    stage: 'Screening',
    documentsUploaded: 4,
    documentsRequired: 12,
    progress: 33,
    submittedAt: '2026-03-05',
    assignedAnalyst: 'Анна Смирнова',
    description: 'AI-платформа для автоматизации финансовых операций',
    industry: 'FinTech',
    stage_funding: 'Pre-Seed',
    team_size: 5,
  },
  {
    id: 'proj-003',
    name: 'GreenEnergy Tech',
    inn: '7703456789',
    status: 'Решение ИК',
    stage: 'IC',
    documentsUploaded: 12,
    documentsRequired: 12,
    progress: 100,
    submittedAt: '2026-02-15',
    assignedAnalyst: 'Иван Петров',
    description: 'Технологии хранения энергии нового поколения',
    industry: 'CleanTech',
    stage_funding: 'Series A',
    team_size: 15,
  },
  {
    id: 'proj-004',
    name: 'EdTech Platform',
    inn: '7704567890',
    status: 'Результат',
    stage: 'Completed',
    documentsUploaded: 12,
    documentsRequired: 12,
    progress: 100,
    submittedAt: '2026-01-20',
    assignedAnalyst: 'Анна Смирнова',
    description: 'Онлайн-платформа для корпоративного обучения',
    industry: 'EdTech',
    stage_funding: 'Seed',
    team_size: 12,
  },
];

export const mockDocuments = [
  { id: 'doc-001', projectId: 'proj-001', name: 'Устав компании', type: 'PDF', status: 'Загружено', uploadedAt: '2026-03-02', validated: true },
  { id: 'doc-002', projectId: 'proj-001', name: 'Выписка из ЕГРЮЛ', type: 'PDF', status: 'Загружено', uploadedAt: '2026-03-02', validated: true },
  { id: 'doc-003', projectId: 'proj-001', name: 'Питч-дек', type: 'PPTX', status: 'Загружено', uploadedAt: '2026-03-01', validated: true },
  { id: 'doc-004', projectId: 'proj-001', name: 'Финансовая модель', type: 'XLSX', status: 'Загружено', uploadedAt: '2026-03-03', validated: true },
  { id: 'doc-005', projectId: 'proj-001', name: 'Патенты и лицензии', type: 'PDF', status: 'Загружено', uploadedAt: '2026-03-04', validated: true },
  { id: 'doc-006', projectId: 'proj-001', name: 'Договоры с ключевыми клиентами', type: 'PDF', status: 'Загружено', uploadedAt: '2026-03-05', validated: true },
  { id: 'doc-007', projectId: 'proj-001', name: 'Отчёт о движении денежных средств', type: 'XLSX', status: 'Загружено', uploadedAt: '2026-03-06', validated: true },
  { id: 'doc-008', projectId: 'proj-001', name: 'Трудовые договоры основателей', type: 'PDF', status: 'Ожидается', uploadedAt: null, validated: false },
  { id: 'doc-009', projectId: 'proj-001', name: 'Справка об отсутствии задолженности', type: 'PDF', status: 'Ожидается', uploadedAt: null, validated: false },
  { id: 'doc-010', projectId: 'proj-001', name: 'Техническая документация', type: 'PDF', status: 'Ожидается', uploadedAt: null, validated: false },
  { id: 'doc-011', projectId: 'proj-001', name: 'Маркетинговый план', type: 'DOCX', status: 'Ожидается', uploadedAt: null, validated: false },
  { id: 'doc-012', projectId: 'proj-001', name: 'Соглашение о конфиденциальности', type: 'PDF', status: 'Ожидается', uploadedAt: null, validated: false },
];

export const mockSummary = {
  projectId: 'proj-001',
  /** Структура согласована с шаблоном «РЕЗЮМЕ ПРОЕКТА» (разд. 1–15); детальные риски — вкладка «Риски». */
  sections: [
    {
      title: '1. Общая информация',
      content:
        'Проект: платформа персонализированной медицины (AI-анализ геномных данных). Стадия: после завершённого НИОКР, подготовка к пилотным внедрениям в клиниках[1]. Документ в системе: черновик резюме (версия по дате выгрузки из кабинета). Якорный научный контур: сотрудничество с лабораторией МГУ и клиникой им. Бурденко по валидации[2][3].',
      sources: [
        { id: 1, url: 'https://e-disclosure.ru', type: 'official' },
        { id: 2, url: 'https://msu.ru', type: 'official' },
        { id: 3, url: 'https://burdenko.ru', type: 'official' },
      ],
      verification: 'confirmed',
    },
    {
      title: '2. Решаемая проблема',
      content:
        'Клиникам и пациентам не хватает доступного и быстрого интерпретирования геномных данных для выбора терапии; существующие сервисы либо узкоспециализированы, либо не дают объяснимого AI-вывода для врачебного решения[4].',
      sources: [{ id: 4, url: 'https://emiss.gov.ru', type: 'official' }],
      verification: 'from_applicant',
    },
    {
      title: '3. Решение, продукт и технология',
      content:
        'B2B SaaS: интерпретация геномных данных с объяснимым отчётом для врача. Ключевой KPI: заявленная точность алгоритма 94% на валидационной выборке[5]. Технологическая цепочка: препарат образца → секвенирование (партнёры) → облачный анализ → отчёт в ЛИС. Остаются критические неопределённости: масштабирование на реальные потоки образцов и интеграции с МИС; планируются дополнительные пилоты в 2–3 клиниках[6]. Детализация производственно-операционных факторов вынесена в матрицу рисков (см. вкладку «Риски»), без повторения здесь.',
      sources: [
        { id: 5, url: 'https://fips.ru', type: 'official' },
        { id: 6, url: 'https://burdenko.ru', type: 'official' },
      ],
      verification: 'confirmed',
    },
    {
      title: '4. Целевой рынок',
      content:
        'Фокус: клиники персонализированной медицины и диагностические сети в РФ; далее — ЕС при подтверждении регуляторики. Оценка рынка сегмента в РФ — порядка $2.3 млрд, CAGR ~15% до 2030 г.; приведены ссылки на отраслевые обзоры[7][8].',
      sources: [
        { id: 7, url: 'https://emiss.gov.ru', type: 'official' },
        { id: 8, url: 'https://rb.ru', type: 'media' },
      ],
      verification: 'confirmed',
    },
    {
      title: '5. Конкуренты и отличия',
      content:
        'Сравнение с Genotek (фокус на потребительскую генетику) и Atlas (диагностические панели): проект позиционируется как решение для клинического решения с акцентом на объяснимость модели и интеграцию в процесс врача, а не только на отчёт для пациента[9]. Количественное сравнение себестоимости и норм расхода заявлено в финмодели (запрос на DD).',
      sources: [{ id: 9, url: 'https://crunchbase.com', type: 'media' }],
      verification: 'from_applicant',
    },
    {
      title: '6. Бизнес-модель и продажи',
      content:
        'Коммерциализация: лицензия на ПО и плата за анализ/клинический отчёт (гибрид продукта и услуги). РФ — основной рынок на 24–36 мес.; выход в ЕС — после CE-стратегии и локальных партнёров[10]. Факт и план выручки: см. раздел «Финансы»; предварительные договорённости: пилотное соглашение с одной сетью клиник (LoI), NDA с двумя лабораториями — на стадии подписания[11].',
      sources: [
        { id: 10, url: 'https://pitchbook.com', type: 'media' },
        { id: 11, url: 'https://e-disclosure.ru', type: 'official' },
      ],
      verification: 'from_applicant',
    },
    {
      title: '7. Команда и партнёры',
      content:
        'Ключевые роли: CEO (ex-Яндекс.Здоровье), CTO (PhD, биоинформатика), медицинский директор (клинический опыт)[12]. Штат: 8 человек, из них 3 PhD[13]. Контрагенты разработки и производства: подрядчик секвенирования, облачный провайдер; маркетинг — внутренний + агентство на проектной основе[14].',
      sources: [
        { id: 12, url: 'https://linkedin.com', type: 'media' },
        { id: 13, url: 'https://e-disclosure.ru', type: 'official' },
        { id: 14, url: 'https://vc.ru', type: 'media' },
      ],
      verification: 'from_applicant',
    },
    {
      title: '8. Финансы и инвестиции',
      content:
        'Привлечено: $500K от бизнес-ангелов (без залогового финансирования по заявлению)[15]. Выручка 2025 (прогноз): $120K[16]. Запрос раунда: $2M на продукт, клинические пилоты и подготовку к выходу в ЕС; основные статьи использования — R&D, регуляторика, команда[17].',
      sources: [
        { id: 15, url: 'https://vc.ru', type: 'media' },
        { id: 16, url: 'https://e-disclosure.ru', type: 'official' },
        { id: 17, url: 'https://pitchbook.com', type: 'media' },
      ],
      verification: 'from_applicant',
    },
    {
      title: '9. Интеллектуальная собственность',
      content:
        'Заявка на изобретение по алгоритму (РФ), стратегия PCT обсуждается[18]. Товарный знак зарегистрирован на физлицо — риск для сделки, см. вкладку «Риски»[19]. Режим ноу-хау: пайплайн обучения и датасеты не раскрываются; план защиты — ограниченный доступ и соглашения с сотрудниками[20].',
      sources: [
        { id: 18, url: 'https://fips.ru', type: 'official' },
        { id: 19, url: 'https://rupto.ru', type: 'official' },
        { id: 20, url: 'https://e-disclosure.ru', type: 'official' },
      ],
      verification: 'unconfirmed',
    },
    {
      title: '10. Регуляторика и сертификация',
      content:
        'ПО медназначения класса 2a (РФ) — в дорожной карте; требования к клиническим данным для расширения показаний уточняются[21]. Экология и промбезопасность для будущей лабораторной площадки — в оценке; перечень разрешений будет закрыт до запуска OPEX-площадки[22].',
      sources: [
        { id: 21, url: 'https://rospotrebnadzor.ru', type: 'official' },
        { id: 22, url: 'https://emiss.gov.ru', type: 'official' },
      ],
      verification: 'from_applicant',
    },
    {
      title: '11. Испытания и валидация',
      content:
        'Проведена валидация алгоритма на когорте клиники им. Бурденко, оформлены отчёты и акты[23]. Запланированы испытания, имитирующие промышленные потоки образцов, — Q3–Q4[24].',
      sources: [
        { id: 23, url: 'https://burdenko.ru', type: 'official' },
        { id: 24, url: 'https://e-disclosure.ru', type: 'official' },
      ],
      verification: 'confirmed',
    },
    {
      title: '12. Активы и инфраструктура',
      content:
        'Существенные активы: облачная инфраструктура (аренда), лицензии на ПО, рабочие станции R&D[25]. Производственная площадка не требуется на текущей стадии; при масштабировании собственной лаборатории планируется аренда площадки класса BSL-2[26].',
      sources: [
        { id: 25, url: 'https://e-disclosure.ru', type: 'official' },
        { id: 26, url: 'https://vc.ru', type: 'media' },
      ],
      verification: 'from_applicant',
    },
    {
      title: '13. Корпоративный статус',
      content:
        'ООО зарегистрировано в РФ; структура участия: три соучредителя с равными долями на старте, опционный пул ESOP 10% (принципиально согласован)[27]. Иностранных юрлиц в капитале нет; корпоративные договоры и опционы — на стадии юридического оформления[28].',
      sources: [
        { id: 27, url: 'https://e-disclosure.ru', type: 'official' },
        { id: 28, url: 'https://kad.arbitr.ru', type: 'official' },
      ],
      verification: 'from_applicant',
    },
    {
      title: 'Сводка по рискам для ИК',
      content:
        'Для быстрого чтения: приоритетные зоны DD — юридическая чистота ИС и товарного знака, налоговый профиль ИП соучредителя, готовность регуляторного трека ПО. Производственно-операционные риски (сырьё, кадры, площадка, оборудование) разобраны по категориям на вкладке «Риски» — здесь не дублируются[29][30][31].',
      sources: [
        { id: 29, url: 'https://rupto.ru', type: 'official' },
        { id: 30, url: 'https://kad.arbitr.ru', type: 'official' },
        { id: 31, url: 'https://whois.ru', type: 'official' },
      ],
      verification: 'unconfirmed',
    },
    {
      title: 'Рекомендации и приложения',
      content:
        'Запросить переоформление товарного знака на юрлицо и независимый аудит финмодели[32]. К пакету DD приложить: протоколы испытаний, ОПИ по алгоритму, подтверждение пилотов — в соответствии с разд. 16 шаблона резюме[33].',
      sources: [
        { id: 32, url: 'https://auditor.ru', type: 'official' },
        { id: 33, url: 'https://e-disclosure.ru', type: 'official' },
      ],
      verification: 'from_applicant',
    },
  ],
  risks: [
    { category: 'legal', severity: 'high', description: 'Товарный знак оформлен на физическое лицо, а не на компанию' },
    { category: 'domain', severity: 'medium', description: 'Домен зарегистрирован менее 1 года назад' },
    { category: 'financial', severity: 'medium', description: 'Один из основателей имеет ИП с налоговой задолженностью' },
    { category: 'team', severity: 'low', description: 'Отсутствует выделенный CTO в команде' },
    {
      category: 'technology',
      severity: 'medium',
      description:
        'Неполнота или необоснованность выбранных технологий. Срыв производственной программы, брак продукции',
    },
    {
      category: 'resource',
      severity: 'medium',
      description:
        'Невозможность обеспечения сырьём российского производства по заявленным спецификациям. Остановка производства, рост себестоимости',
    },
    {
      category: 'personnel',
      severity: 'medium',
      description:
        'Дефицит квалифицированного персонала для работы с выбранным оборудованием. Задержка запуска, снижение качества, аварии',
    },
    {
      category: 'regulatory',
      severity: 'high',
      description:
        'Отсутствие необходимых разрешений (экология, промбезопасность) по нормам РФ. Штрафы, приостановка деятельности, отказ в лицензировании',
    },
    {
      category: 'infrastructure',
      severity: 'medium',
      description:
        'Несоответствие площадки требованиям (коммуникации, логистика, площади). Дополнительные инвестиции, сдвиг сроков',
    },
    {
      category: 'equipment',
      severity: 'medium',
      description:
        'Несовместимость или недостаточная мощность оборудования в технологической цепочке. «Узкие места», простой, недостижение плановой мощности',
    },
  ],
};

/** Стартап без юридического лица (ТЗ1) */
export const documentChecklistWithoutLegalEntity = [
  {
    id: 'nl-r1',
    name: 'Финансовая модель',
    description: 'Прогноз на 3 года с обоснованием допущений',
    format: 'XLSX',
    required: true,
  },
  {
    id: 'nl-r2',
    name: 'Техническая документация',
    description: 'Описание продукта, технологии, архитектуры',
    format: 'PDF',
    required: true,
  },
  {
    id: 'nl-o1',
    name: 'Отчёт о ДДС',
    description: 'Если есть финансовая активность (личные вложения, предзаказы)',
    format: 'XLSX',
    required: false,
  },
  {
    id: 'nl-o2',
    name: 'Патенты и лицензии',
    description: 'Заявки на ИС, свидетельства (могут оформляться на физлиц)',
    format: 'PDF',
    required: false,
  },
  {
    id: 'nl-o3',
    name: 'Предварительные договоры',
    description: 'С клиентами или партнёрами',
    format: 'PDF',
    required: false,
  },
  {
    id: 'nl-o4',
    name: 'Маркетинговый план',
    description: 'Стратегия выхода на рынок и каналы продвижения',
    format: 'DOCX',
    required: false,
  },
  {
    id: 'nl-o5',
    name: 'NDA',
    description: 'Соглашение о конфиденциальности, подписанное с соучредителями/подрядчиками',
    format: 'PDF',
    required: false,
  },
  {
    id: 'nl-o6',
    name: 'Резюме команды',
    description: 'Подтверждение компетенций основателей',
    format: 'PDF',
    required: false,
  },
];

/** Стартап с юридическим лицом (ТЗ1) */
export const documentChecklistWithLegalEntity = [
  {
    id: 'le-r1',
    name: 'Устав компании',
    description: 'Заверенная копия',
    format: 'PDF',
    required: true,
  },
  {
    id: 'le-r2',
    name: 'Выписка из ЕГРЮЛ',
    description: 'Свежая, не старше 30 дней',
    format: 'PDF',
    required: true,
  },
  {
    id: 'le-r3',
    name: 'Финансовая модель',
    description: 'Прогноз на 3 года с детализацией',
    format: 'XLSX',
    required: true,
  },
  {
    id: 'le-r4',
    name: 'Отчёт о ДДС',
    description: 'Факт и прогноз движения денежных средств',
    format: 'XLSX',
    required: true,
  },
  {
    id: 'le-r5',
    name: 'Справка об отсутствии задолженности',
    description: 'Из ФНС',
    format: 'PDF',
    required: true,
  },
  {
    id: 'le-r6',
    name: 'Трудовые договоры / ГПХ',
    description: 'С основателями и ключевыми сотрудниками',
    format: 'PDF',
    required: true,
  },
  {
    id: 'le-o1',
    name: 'Патенты и лицензии',
    description: 'Документы на объекты интеллектуальной собственности',
    format: 'PDF',
    required: false,
  },
  {
    id: 'le-o2',
    name: 'Договоры с клиентами',
    description: 'Ключевые действующие контракты',
    format: 'PDF',
    required: false,
  },
  {
    id: 'le-o3',
    name: 'Техническая документация',
    description: 'Детальные спецификации, схемы, ТЗ',
    format: 'PDF',
    required: false,
  },
  {
    id: 'le-o4',
    name: 'Маркетинговый план',
    description: 'С метриками, юнит-экономикой, бюджетами',
    format: 'DOCX',
    required: false,
  },
  {
    id: 'le-o5',
    name: 'NDA',
    description: 'С контрагентами, сотрудниками, инвесторами',
    format: 'PDF',
    required: false,
  },
  {
    id: 'le-o6',
    name: 'Протоколы собраний учредителей',
    description: 'По ключевым решениям',
    format: 'PDF',
    required: false,
  },
  {
    id: 'le-o7',
    name: 'Лицензии / сертификаты',
    description: 'Если деятельность подлежит лицензированию',
    format: 'PDF',
    required: false,
  },
];

/** История проверенных компаний */
export const checkCompanyHistory = [
  {
    id: 'check-001',
    name: 'ООО "Техно-Инновации"',
    inn: '7701567890',
    url: 'https://techno-innovation.ru',
    requestedAt: '2026-03-15',
    status: 'Анализ завершен',
    findings: 'Положительная оценка. Регулярная финансовая отчетность, активная деятельность.',
    riskLevel: 'Низкий',
  },
  {
    id: 'check-002',
    name: 'АО "СтартМед"',
    inn: '7702456781',
    url: 'https://startmed.ru',
    requestedAt: '2026-03-10',
    status: 'Анализ завершен',
    findings: 'Требует внимания: задолженность перед поставщиками на $50K, есть судебные дела.',
    riskLevel: 'Средний',
  },
  {
    id: 'check-003',
    name: 'ООО "ФинТех Решения"',
    inn: '7703345672',
    url: 'https://fintech-solutions.ru',
    requestedAt: '2026-03-05',
    status: 'Анализ завершен',
    findings: 'Высокий риск: признаки фиктивной деятельности, учредители не найдены.',
    riskLevel: 'Высокий',
  },
  {
    id: 'check-004',
    name: 'ЗАО "ЭнергоИнновация"',
    inn: '7704234563',
    url: null,
    requestedAt: '2026-02-28',
    status: 'На процессе',
    findings: null,
    riskLevel: null,
  },
];

export function getDocumentChecklist(hasLegalEntity) {
  return hasLegalEntity ? documentChecklistWithLegalEntity : documentChecklistWithoutLegalEntity;
}

export const portfolioAlerts = [
  {
    id: 'alert-001',
    type: 'Судебный иск',
    typeColor: 'red',
    company: 'BioTech Solutions',
    title: 'BioTech Solutions — Иск от ИП Пупкина',
    description: 'Сумма иска: 500 000 руб. Дата подачи: 03.05.2026.',
    source: 'КадАрбитр',
    deadlineLabel: 'Срок уведомления LP: 17.05.2026 (10 раб. дней)',
    deadlineColor: 'red',
    action: 'Сформировать уведомление',
  },
  {
    id: 'alert-002',
    type: 'Корпоративное событие',
    typeColor: 'amber',
    company: 'EdTech Platform',
    title: 'EdTech Platform — Истечение полномочий Гендиректора',
    description: 'Полномочия истекают через 30 дней (05.06.2026).',
    source: 'ЕГРЮЛ',
    deadlineLabel: 'Требуется решение общего собрания',
    deadlineColor: 'amber',
    action: 'Создать задачу юристу',
  },
  {
    id: 'alert-003',
    type: 'Налоговая проверка',
    typeColor: 'orange',
    company: 'BioTech Solutions',
    title: 'BioTech Solutions — Камеральная проверка',
    description: 'Запрос документов по НДС за 1 квартал 2026.',
    source: 'ФНС',
    deadlineLabel: 'Срок ответа: 5 дней',
    deadlineColor: 'orange',
    action: 'Загрузить ответ',
  },
];

export const portfolioCompanies = [
  {
    id: 'port-001',
    projectId: 'proj-004',
    name: 'EdTech Platform',
    inn: '7704567890',
    shortName: 'EP',
    colorClass: 'bg-indigo-900/[.40] text-indigo-400',
    modalBg: 'bg-indigo-600',
    tags: ['EdTech', 'Series A'],
    description: 'Онлайн-платформа для корпоративного обучения. Series A.',
    industry: 'EdTech',
    fundShare: '12%',
    entryDate: '20.01.2026',
    statusLabel: 'Активная',
    alertType: null,
    alertLabel: 'Все отчёты предоставлены',
    metrics: [
      { label: 'Выручка (LTM)', value: '85 млн ₽' },
      { label: 'Чистая прибыль', value: '+8 млн ₽', positive: true },
      { label: 'Burn Rate', value: '1.2 млн ₽/мес' },
    ],
    aiSummary: 'Компания показывает устойчивый рост: +30% YoY по числу корпоративных клиентов. Юридических рисков не выявлено. Все отчёты перед LP предоставлены в срок. Рекомендовано рассмотреть follow-on инвестицию в Series B.',
    events: [
      { date: '15 Апр 2026', source: 'Внутренний документ', dotColor: 'bg-primary', title: 'Предоставлен ежеквартальный отчёт Q1 2026', description: 'Принят LP без замечаний.' },
      { date: '20 Янв 2026', source: 'ЕГРЮЛ', dotColor: 'bg-green-500', title: 'Завершена инвестиционная сделка', description: 'Доля фонда 12% зафиксирована в SHA.' },
    ],
    documents: [
      { name: 'Q1_2026_Report.pdf', icon: 'file-text', iconColor: 'text-red-400', type: 'Отчёт', date: '15.04.2026', status: 'Актуально', statusClass: 'bg-green-900/[.30] text-green-400' },
      { name: 'SHA_Agreement.pdf', icon: 'file-text', iconColor: 'text-red-400', type: 'Договор', date: '20.01.2026', status: 'Архив', statusClass: 'bg-[#333] text-text-secondary' },
      { name: 'Pitch_Deck_SeriesA.pptx', icon: 'presentation', iconColor: 'text-orange-400', type: 'Презентация', date: '10.01.2026', status: 'Архив', statusClass: 'bg-[#333] text-text-secondary' },
    ],
    icDecisions: [
      { date: '20.01.2026', title: 'Одобрение инвестиции Series A', description: 'Сумма: $1.5M. Оценка: $12M Post-money.', note: null, borderColor: 'border-green-500' },
    ],
    shaObligations: [
      { title: 'Предоставление ежеквартальной отчётности', description: 'Срок: до 15 числа месяца, следующего за отчётным кварталом.' },
      { title: 'Уведомление о судебных спорах > 100 тыс. руб.', description: 'Срок: в течение 10 рабочих дней с момента получения информации.' },
      { title: 'Согласование изменения бизнес-плана', description: 'Требуется письменное согласие инвестора при отклонении бюджета > 15%.' },
    ],
  },
  {
    id: 'port-002',
    projectId: null,
    name: 'ООО «СтартапХ»',
    inn: '7707083893',
    shortName: 'SX',
    colorClass: 'bg-blue-900/[.40] text-blue-400',
    modalBg: 'bg-blue-600',
    tags: ['Logistics Tech', 'Series A'],
    description: 'Разработка ПО для автоматизации логистики. Series A.',
    industry: 'Logistics Tech',
    fundShare: '15%',
    entryDate: '12.03.2024',
    statusLabel: 'Активная',
    alertType: 'danger',
    alertLabel: 'Есть активный судебный иск',
    metrics: [
      { label: 'Выручка (LTM)', value: '120 млн ₽' },
      { label: 'Чистая прибыль', value: '+15 млн ₽', positive: true },
      { label: 'Burn Rate', value: '2.5 млн ₽/мес' },
    ],
    aiSummary: 'Компания демонстрирует рост выручки на 25% YoY. Однако выявлен юридический риск: подан иск от контрагента на сумму 500 тыс. руб. (менее 1% от годовой выручки). Риск признан умеренным. Требуется контроль сроков предоставления отчётности инвесторам согласно договору SHA.',
    events: [
      { date: '03 Мая 2026', source: 'КадАрбитр', dotColor: 'bg-red-500', title: 'Подан иск А40-12345/2026', description: 'Истец: ИП Пупкин. Предмет: Неоплата услуг.' },
      { date: '15 Апр 2026', source: 'Внутренний документ', dotColor: 'bg-primary', title: 'Обновлена Финансовая Модель v2.4', description: 'Согласовано CFO фонда. Требуется отправка LP.' },
      { date: '10 Мар 2026', source: 'ЕГРЮЛ', dotColor: 'bg-green-500', title: 'Смена юридического адреса', description: 'Изменения внесены в реестр.' },
    ],
    documents: [
      { name: 'Financial_Model_v2.4.xlsx', icon: 'file-spreadsheet', iconColor: 'text-green-400', type: 'Финмодель', date: '15.04.2026', status: 'Актуально', statusClass: 'bg-green-900/[.30] text-green-400' },
      { name: 'SHA_Agreement_Signed.pdf', icon: 'file-text', iconColor: 'text-red-400', type: 'Договор', date: '12.03.2024', status: 'Архив', statusClass: 'bg-[#333] text-text-secondary' },
      { name: 'Pitch_Deck_SeriesA.pptx', icon: 'presentation', iconColor: 'text-orange-400', type: 'Презентация', date: '10.01.2024', status: 'Архив', statusClass: 'bg-[#333] text-text-secondary' },
    ],
    icDecisions: [
      { date: '12.03.2024', title: 'Одобрение инвестиции Series A', description: 'Сумма: $2M. Оценка: $10M Post-money.', note: 'Особое мнение (Иванов И.И.): обратить внимание на зависимость от одного крупного клиента (>40% выручки). Запросить план диверсификации.', borderColor: 'border-green-500' },
      { date: '15.06.2023', title: 'Seed Round Investment', description: 'Сумма: $500K. Convertible Note.', note: null, borderColor: 'border-primary' },
    ],
    shaObligations: [
      { title: 'Предоставление ежеквартальной отчётности', description: 'Срок: до 15 числа месяца, следующего за отчётным кварталом.' },
      { title: 'Уведомление о судебных спорах > 100 тыс. руб.', description: 'Срок: в течение 10 рабочих дней с момента получения информации.' },
      { title: 'Согласование изменения бизнес-плана', description: 'Требуется письменное согласие инвестора при отклонении бюджета > 15%.' },
    ],
  },
  {
    id: 'port-003',
    projectId: null,
    name: 'АО «ФинТех Солюшнс»',
    inn: '7702345678',
    shortName: 'FT',
    colorClass: 'bg-purple-900/[.40] text-purple-400',
    modalBg: 'bg-purple-600',
    tags: ['FinTech', 'Seed'],
    description: 'Платежный шлюз для e-commerce. Seed round.',
    industry: 'FinTech',
    fundShare: '8%',
    entryDate: '05.09.2023',
    statusLabel: 'Активная',
    alertType: 'warning',
    alertLabel: 'Истекают полномочия CEO',
    metrics: [
      { label: 'Выручка (LTM)', value: '45 млн ₽' },
      { label: 'Чистая прибыль', value: '+3 млн ₽', positive: true },
      { label: 'Burn Rate', value: '0.8 млн ₽/мес' },
    ],
    aiSummary: 'Компания стабильно растёт в сегменте платёжных решений для e-commerce. Ключевой риск — истечение полномочий гендиректора Иванова И.И. через 30 дней. Требуется подготовка протокола ОСА и пролонгация договора. Финансовые показатели в норме.',
    events: [
      { date: '05 Май 2026', source: 'ЕГРЮЛ', dotColor: 'bg-amber-500', title: 'Уведомление об истечении полномочий CEO', description: 'Полномочия Иванова И.И. истекают 05.06.2026. Требуется решение ОСА.' },
      { date: '01 Мар 2026', source: 'Внутренний документ', dotColor: 'bg-primary', title: 'Согласован договор займа с банком-партнёром', description: 'Кредитная линия $500K на 12 месяцев.' },
      { date: '05 Сен 2023', source: 'Внутренний документ', dotColor: 'bg-green-500', title: 'Завершена инвестиционная сделка Seed', description: 'Доля фонда 8% зафиксирована в SHA.' },
    ],
    documents: [
      { name: 'SHA_Agreement_FT.pdf', icon: 'file-text', iconColor: 'text-red-400', type: 'Договор', date: '05.09.2023', status: 'Актуально', statusClass: 'bg-green-900/[.30] text-green-400' },
      { name: 'Financial_Model_Q1.xlsx', icon: 'file-spreadsheet', iconColor: 'text-green-400', type: 'Финмодель', date: '10.04.2026', status: 'Актуально', statusClass: 'bg-green-900/[.30] text-green-400' },
    ],
    icDecisions: [
      { date: '05.09.2023', title: 'Одобрение Seed инвестиции', description: 'Сумма: $800K. Оценка: $4M Pre-money.', note: null, borderColor: 'border-green-500' },
    ],
    shaObligations: [
      { title: 'Предоставление полугодовой отчётности', description: 'Срок: до 31 июля и 31 января ежегодно.' },
      { title: 'Согласование ключевых сделок', description: 'Любые сделки свыше $200K требуют одобрения инвестора.' },
      { title: 'Уведомление о смене ключевых менеджеров', description: 'Срок: в течение 5 рабочих дней.' },
    ],
  },
  {
    id: 'port-004',
    projectId: null,
    name: 'ООО «БиоТех Лаб»',
    inn: '7701234567',
    shortName: 'BT',
    colorClass: 'bg-emerald-900/[.40] text-emerald-400',
    modalBg: 'bg-emerald-600',
    tags: ['CleanTech', 'Pre-seed'],
    description: 'Производство биоразлагаемых материалов. Pre-seed.',
    industry: 'CleanTech',
    fundShare: '10%',
    entryDate: '20.01.2025',
    statusLabel: 'Активная',
    alertType: null,
    alertLabel: 'Риски не выявлены',
    metrics: [
      { label: 'Выручка (LTM)', value: '12 млн ₽' },
      { label: 'Чистая прибыль', value: '-2 млн ₽', positive: false },
      { label: 'Burn Rate', value: '0.5 млн ₽/мес' },
    ],
    aiSummary: 'Компания находится на ранней стадии коммерциализации. Первые пилотные продажи с двумя промышленными клиентами. Налоговых и юридических рисков не выявлено. Камеральная проверка ФНС по НДС за Q1 2026 — в процессе, срок ответа 5 рабочих дней.',
    events: [
      { date: '12 Май 2026', source: 'ФНС', dotColor: 'bg-orange-500', title: 'Камеральная проверка НДС Q1 2026', description: 'Запрос документов. Срок ответа: 5 рабочих дней.' },
      { date: '15 Мар 2026', source: 'Внутренний документ', dotColor: 'bg-primary', title: 'Первые коммерческие продажи', description: 'Подписаны договоры с 2 пилотными клиентами.' },
      { date: '20 Янв 2025', source: 'Внутренний документ', dotColor: 'bg-green-500', title: 'Завершена инвестиционная сделка Pre-seed', description: 'Доля фонда 10% зафиксирована в SHA.' },
    ],
    documents: [
      { name: 'SHA_BioTech.pdf', icon: 'file-text', iconColor: 'text-red-400', type: 'Договор', date: '20.01.2025', status: 'Актуально', statusClass: 'bg-green-900/[.30] text-green-400' },
      { name: 'Technical_Spec_v1.pdf', icon: 'file-text', iconColor: 'text-red-400', type: 'Техдокументация', date: '05.01.2025', status: 'Актуально', statusClass: 'bg-green-900/[.30] text-green-400' },
    ],
    icDecisions: [
      { date: '20.01.2025', title: 'Одобрение Pre-seed инвестиции', description: 'Сумма: $300K. SAFE с оценкой $3M Cap.', note: 'Особое мнение: запросить план выхода на безубыточность в течение 18 месяцев.', borderColor: 'border-green-500' },
    ],
    shaObligations: [
      { title: 'Предоставление ежеквартальной отчётности', description: 'Срок: до 15 числа месяца, следующего за отчётным кварталом.' },
      { title: 'Уведомление об изменении состава учредителей', description: 'Срок: в течение 5 рабочих дней.' },
    ],
  },
];

export const lpObligations = [
  {
    id: 'ob-001',
    type: 'Ежеквартальный отчет',
    entity: 'Investment Partnership I',
    deadline: '15 Мая 2026',
    status: 'ready',
    statusLabel: 'Готов к отправке',
    action: 'Отправить LP',
  },
  {
    id: 'ob-002',
    type: 'Обновленная финмодель',
    entity: 'ООО «СтартапХ»',
    deadline: '06 Мая 2026',
    status: 'overdue',
    statusLabel: 'Просрочено',
    action: 'Сгенерировать письмо',
  },
  {
    id: 'ob-003',
    type: 'Уведомление о судебном споре',
    entity: 'ООО «СтартапХ»',
    deadline: '17 Мая 2026',
    status: 'in_progress',
    statusLabel: 'В работе',
    action: 'Черновик готов',
  },
  {
    id: 'ob-004',
    type: 'Годовой финансовый отчет',
    entity: 'Investment Partnership II',
    deadline: '30 Июня 2026',
    status: 'planned',
    statusLabel: 'Запланировано',
    action: 'Начать подготовку',
  },
];
