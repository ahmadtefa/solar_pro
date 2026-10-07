import 'package:flutter/material.dart';

import '../../shared/resource/resource_config.dart';

/// Master data of the platform layer: organisation, geography, money, taxes,
/// document setup, fiscal calendar and security.
///
/// Field and column keys mirror the database columns exactly; the API returns
/// them verbatim, so a typo here would simply show an empty cell.
class PlatformConfigs {
  const PlatformConfigs._();

  static Map<String, ResourceConfig> all() => <String, ResourceConfig>{
        'branches': branches,
        'departments': departments,
        'divisions': divisions,
        'cost-centers': costCenters,
        'countries': countries,
        'cities': cities,
        'addresses': addresses,
        'currencies': currencies,
        'exchange-rates': exchangeRates,
        'taxes': taxes,
        'payment-terms': paymentTerms,
        'units': units,
        'unit-groups': unitGroups,
        'unit-conversions': unitConversions,
        'document-types': documentTypes,
        'numbering': numbering,
        'fiscal-years': fiscalYears,
        'fiscal-periods': fiscalPeriods,
        'settings': settings,
        'users': users,
        'roles': roles,
        'audit-logs': auditLogs,
        'companies': companies,
      };

  // ------------------------------------------------------------ organisation
  static const ResourceConfig branches = ResourceConfig(
    nameKey: 'common.branch',
    path: '/branches',
    permissionPrefix: 'core.branch',
    icon: Icons.account_tree_outlined,
    breadcrumbs: <String>['nav.settings', 'settings.organisation'],
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 110, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('name_ar', 'common.name_ar', width: 200),
      ColumnSpec('is_head_office', 'settings.organisation', type: FieldType.boolean, width: 110),
      ColumnSpec('phone', 'common.reference', width: 140),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'is_head_office', labelKey: 'settings.organisation', type: FieldType.boolean),
      FieldSpec(key: 'address_line1', labelKey: 'common.description', span: 2),
      FieldSpec(key: 'city_id', labelKey: 'common.city', type: FieldType.reference, optionsKey: 'lookup:cities'),
      FieldSpec(key: 'country_code', labelKey: 'common.country', type: FieldType.reference, optionsKey: 'lookup:countries'),
      FieldSpec(key: 'phone', labelKey: 'common.reference'),
      FieldSpec(key: 'email', labelKey: 'login.email'),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
    exportEntity: 'branches',
  );

  static const ResourceConfig departments = ResourceConfig(
    nameKey: 'common.department',
    path: '/departments',
    permissionPrefix: 'core.department',
    icon: Icons.hub_outlined,
    breadcrumbs: <String>['nav.settings', 'settings.organisation'],
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 110, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('name_ar', 'common.name_ar', width: 200),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'branch_id', labelKey: 'common.branch', type: FieldType.reference, optionsKey: 'lookup:branches'),
      FieldSpec(key: 'cost_center_id', labelKey: 'common.cost_center', type: FieldType.reference, optionsKey: 'lookup:cost-centers'),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig divisions = ResourceConfig(
    nameKey: 'nav.master_data',
    path: '/divisions',
    permissionPrefix: 'core.division',
    icon: Icons.call_split_outlined,
    breadcrumbs: <String>['nav.settings', 'settings.organisation'],
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 110, emphasize: true),
      ColumnSpec('name', 'common.name', width: 240),
      ColumnSpec('name_ar', 'common.name_ar', width: 220),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'branch_id', labelKey: 'common.branch', type: FieldType.reference, optionsKey: 'lookup:branches'),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig costCenters = ResourceConfig(
    nameKey: 'common.cost_center',
    path: '/cost-centers',
    permissionPrefix: 'core.cost_center',
    icon: Icons.pie_chart_outline,
    breadcrumbs: <String>['nav.settings', 'settings.organisation'],
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 120, emphasize: true),
      ColumnSpec('name', 'common.name', width: 240),
      ColumnSpec('name_ar', 'common.name_ar', width: 220),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'branch_id', labelKey: 'common.branch', type: FieldType.reference, optionsKey: 'lookup:branches'),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  // ------------------------------------------------------------- geography
  static const ResourceConfig countries = ResourceConfig(
    nameKey: 'nav.master_data',
    path: '/geo/countries',
    permissionPrefix: 'core.country',
    icon: Icons.public,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 90, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('name_ar', 'common.name_ar', width: 200),
      ColumnSpec('phone_code', 'common.reference', width: 100),
      ColumnSpec('default_currency_code', 'common.currency', width: 110),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'phone_code', labelKey: 'common.reference'),
      FieldSpec(
        key: 'default_currency_code',
        labelKey: 'common.currency',
        type: FieldType.reference,
        optionsKey: 'lookup:currencies',
      ),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig cities = ResourceConfig(
    nameKey: 'nav.master_data',
    path: '/geo/cities',
    permissionPrefix: 'core.city',
    icon: Icons.location_city_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 110, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('name_ar', 'common.name_ar', width: 200),
      ColumnSpec('country_code', 'common.country', width: 120),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code'),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(
        key: 'country_code',
        labelKey: 'common.country',
        type: FieldType.reference,
        required: true,
        optionsKey: 'lookup:countries',
      ),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig addresses = ResourceConfig(
    nameKey: 'common.details',
    path: '/geo/addresses',
    permissionPrefix: 'core.address',
    icon: Icons.map_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('party_type', 'common.party', width: 120),
      ColumnSpec('label', 'common.name', width: 160, emphasize: true),
      ColumnSpec('address_line1', 'common.description', width: 240),
      ColumnSpec('city', 'common.city', width: 140),
      ColumnSpec('country_code', 'common.country', width: 110),
      ColumnSpec('is_primary', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(
        key: 'party_type',
        labelKey: 'common.party',
        type: FieldType.select,
        options: <DropdownOption>[
          DropdownOption('customer', 'common.customer'),
          DropdownOption('supplier', 'common.supplier'),
          DropdownOption('employee', 'common.employee'),
          DropdownOption('company', 'common.company'),
          DropdownOption('branch', 'common.branch'),
        ],
      ),
      FieldSpec(key: 'party_id', labelKey: 'common.party', required: true),
      FieldSpec(key: 'label', labelKey: 'common.name'),
      FieldSpec(key: 'address_line1', labelKey: 'common.description', span: 2),
      FieldSpec(key: 'city', labelKey: 'common.city'),
      FieldSpec(key: 'country_code', labelKey: 'common.country', type: FieldType.reference, optionsKey: 'lookup:countries'),
      FieldSpec(key: 'postal_code', labelKey: 'common.code'),
      FieldSpec(key: 'is_primary', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  // ----------------------------------------------------------------- money
  static const ResourceConfig currencies = ResourceConfig(
    nameKey: 'settings.currencies',
    path: '/currencies',
    permissionPrefix: 'core.currency',
    icon: Icons.currency_exchange,
    breadcrumbs: <String>['nav.settings', 'settings.currencies'],
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 90, emphasize: true),
      ColumnSpec('name', 'common.name', width: 200),
      ColumnSpec('name_ar', 'common.name_ar', width: 180),
      ColumnSpec('symbol', 'common.reference', width: 80),
      ColumnSpec('decimal_places', 'common.quantity', type: FieldType.integer, width: 100),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'symbol', labelKey: 'common.reference'),
      FieldSpec(key: 'decimal_places', labelKey: 'common.quantity', type: FieldType.integer, defaultValue: 2),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig exchangeRates = ResourceConfig(
    nameKey: 'settings.currencies',
    path: '/exchange-rates',
    permissionPrefix: 'core.exchange_rate',
    icon: Icons.swap_horiz,
    breadcrumbs: <String>['nav.settings', 'settings.currencies'],
    columns: <ColumnSpec>[
      ColumnSpec('currency_code', 'common.currency', width: 110, emphasize: true),
      ColumnSpec('base_currency_code', 'common.currency', width: 120),
      ColumnSpec('rate', 'common.price', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('rate_type', 'common.status', width: 110),
      ColumnSpec('effective_from', 'common.from', type: FieldType.date, width: 130),
      ColumnSpec('effective_to', 'common.to', type: FieldType.date, width: 130),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'currency_code', labelKey: 'common.currency', required: true, optionsKey: 'lookup:currencies', type: FieldType.reference),
      FieldSpec(key: 'base_currency_code', labelKey: 'common.currency', required: true, optionsKey: 'lookup:currencies', type: FieldType.reference),
      FieldSpec(key: 'rate', labelKey: 'common.price', type: FieldType.decimal, required: true),
      FieldSpec(
        key: 'rate_type',
        labelKey: 'common.status',
        type: FieldType.select,
        options: <DropdownOption>[
          DropdownOption('spot', 'common.today'),
          DropdownOption('average', 'common.this_month'),
          DropdownOption('historical', 'common.custom_range'),
        ],
        defaultValue: 'spot',
      ),
      FieldSpec(key: 'effective_from', labelKey: 'common.from', type: FieldType.date, required: true),
      FieldSpec(key: 'effective_to', labelKey: 'common.to', type: FieldType.date),
    ],
  );

  static const ResourceConfig taxes = ResourceConfig(
    nameKey: 'settings.taxes',
    path: '/taxes',
    permissionPrefix: 'core.tax',
    icon: Icons.percent,
    breadcrumbs: <String>['nav.settings', 'settings.taxes'],
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 100, emphasize: true),
      ColumnSpec('name', 'common.name', width: 200),
      ColumnSpec('rate', 'common.tax', type: FieldType.decimal, width: 100, align: MainAxisAlignment.end),
      ColumnSpec('tax_type', 'common.status', width: 110),
      ColumnSpec('inclusion', 'common.status', width: 110),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'rate', labelKey: 'common.tax', type: FieldType.decimal, required: true),
      FieldSpec(
        key: 'tax_type',
        labelKey: 'common.status',
        type: FieldType.select,
        options: <DropdownOption>[
          DropdownOption('sales', 'nav.sales'),
          DropdownOption('purchase', 'nav.purchasing'),
          DropdownOption('withholding', 'common.tax'),
          DropdownOption('both', 'common.all'),
        ],
        defaultValue: 'sales',
      ),
      FieldSpec(
        key: 'inclusion',
        labelKey: 'common.status',
        type: FieldType.select,
        options: <DropdownOption>[
          DropdownOption('exclusive', 'common.tax'),
          DropdownOption('inclusive', 'common.total'),
        ],
        defaultValue: 'exclusive',
      ),
      FieldSpec(key: 'effective_from', labelKey: 'common.from', type: FieldType.date),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
    exportEntity: 'taxes',
  );

  static const ResourceConfig paymentTerms = ResourceConfig(
    nameKey: 'nav.master_data',
    path: '/payment-terms',
    permissionPrefix: 'core.payment_term',
    icon: Icons.schedule_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 110, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('days', 'common.quantity', type: FieldType.integer, width: 100),
      ColumnSpec('discount_days', 'common.quantity', type: FieldType.integer, width: 120),
      ColumnSpec('discount_percent', 'common.discount', type: FieldType.decimal, width: 120),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'days', labelKey: 'common.quantity', type: FieldType.integer, required: true, defaultValue: 30),
      FieldSpec(key: 'discount_days', labelKey: 'common.quantity', type: FieldType.integer),
      FieldSpec(key: 'discount_percent', labelKey: 'common.discount', type: FieldType.decimal),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
    exportEntity: 'payment_terms',
  );

  // ------------------------------------------------------------------ units
  static const ResourceConfig units = ResourceConfig(
    nameKey: 'settings.units',
    path: '/units',
    permissionPrefix: 'core.unit',
    icon: Icons.straighten,
    breadcrumbs: <String>['nav.settings', 'settings.units'],
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 100, emphasize: true),
      ColumnSpec('name', 'common.name', width: 200),
      ColumnSpec('symbol', 'common.reference', width: 90),
      ColumnSpec('is_base', 'common.active', type: FieldType.boolean, width: 90),
      ColumnSpec('allow_fraction', 'common.active', type: FieldType.boolean, width: 110),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'symbol', labelKey: 'common.reference'),
      FieldSpec(key: 'unit_group_id', labelKey: 'settings.units', type: FieldType.reference, optionsKey: 'list:/unit-groups#name'),
      FieldSpec(key: 'is_base', labelKey: 'common.active', type: FieldType.boolean),
      FieldSpec(key: 'allow_fraction', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig unitGroups = ResourceConfig(
    nameKey: 'settings.units',
    path: '/unit-groups',
    permissionPrefix: 'core.unit_group',
    icon: Icons.category_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 110, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'base_unit_id', labelKey: 'settings.units', type: FieldType.reference, optionsKey: 'list:/units#name'),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig unitConversions = ResourceConfig(
    nameKey: 'settings.units',
    path: '/unit-conversions',
    permissionPrefix: 'core.unit_conversion',
    icon: Icons.compare_arrows,
    columns: <ColumnSpec>[
      ColumnSpec('from_unit_id', 'common.from', width: 150),
      ColumnSpec('to_unit_id', 'common.to', width: 150),
      ColumnSpec('factor', 'common.quantity', type: FieldType.decimal, width: 130, align: MainAxisAlignment.end),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'from_unit_id', labelKey: 'common.from', type: FieldType.reference, required: true, optionsKey: 'list:/units#name'),
      FieldSpec(key: 'to_unit_id', labelKey: 'common.to', type: FieldType.reference, required: true, optionsKey: 'list:/units#name'),
      FieldSpec(key: 'factor', labelKey: 'common.quantity', type: FieldType.decimal, required: true),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  // -------------------------------------------------------- document setup
  static const ResourceConfig documentTypes = ResourceConfig(
    nameKey: 'common.document_no',
    path: '/document-types',
    permissionPrefix: 'core.document_type',
    icon: Icons.description_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 130, emphasize: true),
      ColumnSpec('name', 'common.name', width: 220),
      ColumnSpec('module', 'nav.settings', width: 130),
      ColumnSpec('requires_approval', 'action.approve', type: FieldType.boolean, width: 120),
      ColumnSpec('affects_inventory', 'nav.inventory', type: FieldType.boolean, width: 120),
      ColumnSpec('affects_accounting', 'nav.accounting', type: FieldType.boolean, width: 130),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'module', labelKey: 'nav.settings'),
      FieldSpec(key: 'requires_approval', labelKey: 'action.approve', type: FieldType.boolean),
      FieldSpec(key: 'affects_inventory', labelKey: 'nav.inventory', type: FieldType.boolean),
      FieldSpec(key: 'affects_accounting', labelKey: 'nav.accounting', type: FieldType.boolean),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig numbering = ResourceConfig(
    nameKey: 'settings.numbering',
    path: '/numbering',
    permissionPrefix: 'core.number_sequence',
    icon: Icons.numbers,
    breadcrumbs: <String>['nav.settings', 'settings.numbering'],
    canDelete: false,
    columns: <ColumnSpec>[
      ColumnSpec('document_type', 'common.document_no', width: 180, emphasize: true),
      ColumnSpec('prefix', 'common.reference', width: 100),
      ColumnSpec('suffix', 'common.reference', width: 100),
      ColumnSpec('padding', 'common.quantity', type: FieldType.integer, width: 90),
      ColumnSpec('next_number', 'common.page', type: FieldType.integer, width: 110),
      ColumnSpec('reset_yearly', 'common.yes', type: FieldType.boolean, width: 110),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'document_type', labelKey: 'common.document_no', required: true),
      FieldSpec(key: 'prefix', labelKey: 'common.reference'),
      FieldSpec(key: 'suffix', labelKey: 'common.reference'),
      FieldSpec(key: 'padding', labelKey: 'common.quantity', type: FieldType.integer, defaultValue: 5),
      FieldSpec(key: 'next_number', labelKey: 'common.page', type: FieldType.integer, defaultValue: 1),
      FieldSpec(key: 'reset_yearly', labelKey: 'common.yes', type: FieldType.boolean),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  // ---------------------------------------------------------------- fiscal
  static const ResourceConfig fiscalYears = ResourceConfig(
    nameKey: 'common.period',
    path: '/fiscal-years',
    permissionPrefix: 'core.fiscal_year',
    icon: Icons.calendar_month_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 110, emphasize: true),
      ColumnSpec('name', 'common.name', width: 200),
      ColumnSpec('start_date', 'common.from', type: FieldType.date, width: 130),
      ColumnSpec('end_date', 'common.to', type: FieldType.date, width: 130),
      ColumnSpec('status', 'common.status', isStatus: true, width: 110),
      ColumnSpec('is_closed', 'common.status', type: FieldType.boolean, width: 100),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'start_date', labelKey: 'common.from', type: FieldType.date, required: true),
      FieldSpec(key: 'end_date', labelKey: 'common.to', type: FieldType.date, required: true),
    ],
  );

  static const ResourceConfig fiscalPeriods = ResourceConfig(
    nameKey: 'common.period',
    path: '/fiscal-periods',
    permissionPrefix: 'core.fiscal_period',
    icon: Icons.date_range_outlined,
    columns: <ColumnSpec>[
      ColumnSpec('period_number', 'common.page', type: FieldType.integer, width: 100),
      ColumnSpec('name', 'common.name', width: 180),
      ColumnSpec('start_date', 'common.from', type: FieldType.date, width: 130),
      ColumnSpec('end_date', 'common.to', type: FieldType.date, width: 130),
      ColumnSpec('is_closed', 'common.status', type: FieldType.boolean, width: 110),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'fiscal_year_id', labelKey: 'common.period', required: true),
      FieldSpec(key: 'period_number', labelKey: 'common.page', type: FieldType.integer, required: true),
      FieldSpec(key: 'name', labelKey: 'common.name'),
      FieldSpec(key: 'start_date', labelKey: 'common.from', type: FieldType.date, required: true),
      FieldSpec(key: 'end_date', labelKey: 'common.to', type: FieldType.date, required: true),
    ],
  );

  // -------------------------------------------------------------- security
  static const ResourceConfig settings = ResourceConfig(
    nameKey: 'settings.title',
    path: '/settings',
    permissionPrefix: 'core.system_setting',
    icon: Icons.tune,
    canCreate: true,
    canDelete: false,
    columns: <ColumnSpec>[
      ColumnSpec('key', 'common.code', width: 240, emphasize: true),
      ColumnSpec('value', 'common.details', width: 260),
      ColumnSpec('category', 'common.status', width: 140),
      ColumnSpec('scope', 'common.status', width: 120),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'key', labelKey: 'common.code', required: true),
      FieldSpec(key: 'value', labelKey: 'common.details', span: 2),
      FieldSpec(key: 'category', labelKey: 'common.status'),
      FieldSpec(key: 'scope', labelKey: 'common.status', defaultValue: 'company'),
    ],
  );

  static const ResourceConfig users = ResourceConfig(
    nameKey: 'settings.users',
    path: '/users',
    permissionPrefix: 'core.user',
    icon: Icons.people_outline,
    breadcrumbs: <String>['nav.admin', 'settings.users'],
    columns: <ColumnSpec>[
      ColumnSpec('email', 'login.email', width: 220, emphasize: true),
      ColumnSpec('full_name', 'common.name', width: 200),
      ColumnSpec('job_title', 'common.details', width: 160),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
      ColumnSpec('is_superuser', 'nav.admin', type: FieldType.boolean, width: 110),
      ColumnSpec('last_login_at', 'common.date', type: FieldType.dateTime, width: 160),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'email', labelKey: 'login.email', required: true),
      FieldSpec(key: 'full_name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'full_name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'password', labelKey: 'login.password', helpKey: 'common.optional'),
      FieldSpec(key: 'job_title', labelKey: 'common.details'),
      FieldSpec(key: 'phone', labelKey: 'common.reference'),
      FieldSpec(key: 'language', labelKey: 'common.language', type: FieldType.select, options: <DropdownOption>[
        DropdownOption('ar', 'common.language'),
        DropdownOption('en', 'common.language'),
      ]),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig roles = ResourceConfig(
    nameKey: 'settings.roles',
    path: '/roles',
    permissionPrefix: 'core.role',
    icon: Icons.shield_outlined,
    breadcrumbs: <String>['nav.admin', 'settings.roles'],
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 160, emphasize: true),
      ColumnSpec('name', 'common.name', width: 200),
      ColumnSpec('name_ar', 'common.name_ar', width: 180),
      ColumnSpec('level', 'common.quantity', type: FieldType.integer, width: 90),
      ColumnSpec('data_scope', 'common.status', width: 130),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'description', labelKey: 'common.description', span: 2),
      FieldSpec(key: 'level', labelKey: 'common.quantity', type: FieldType.integer, defaultValue: 10),
      FieldSpec(
        key: 'data_scope',
        labelKey: 'common.status',
        type: FieldType.select,
        options: <DropdownOption>[
          DropdownOption('company', 'common.company'),
          DropdownOption('branch', 'common.branch'),
          DropdownOption('warehouse', 'common.warehouse'),
          DropdownOption('own', 'common.my_account'),
        ],
        defaultValue: 'company',
      ),
      FieldSpec(key: 'is_active', labelKey: 'common.active', type: FieldType.boolean, defaultValue: true),
    ],
  );

  static const ResourceConfig auditLogs = ResourceConfig(
    nameKey: 'nav.audit',
    path: '/audit-logs',
    permissionPrefix: 'core.audit_log',
    icon: Icons.history,
    readOnly: true,
    canCreate: false,
    canEdit: false,
    canDelete: false,
    filters: <FilterSpec>[
      FilterSpec(key: 'entity_type', labelKey: 'common.details'),
      FilterSpec(key: 'action', labelKey: 'common.status'),
      FilterSpec(key: 'date_from', labelKey: 'common.from', type: FieldType.date, queryParam: 'date_from'),
    ],
    columns: <ColumnSpec>[
      ColumnSpec('created_at', 'common.date', type: FieldType.dateTime, width: 170, emphasize: true),
      ColumnSpec('action', 'common.status', width: 130),
      ColumnSpec('entity_type', 'common.details', width: 150),
      ColumnSpec('entity_label', 'common.name', width: 200),
      ColumnSpec('user_name', 'common.created_by', width: 170),
      ColumnSpec('ip_address', 'session.ip', width: 130),
    ],
  );

  static const ResourceConfig companies = ResourceConfig(
    nameKey: 'settings.company',
    path: '/admin/companies',
    permissionPrefix: 'core.company',
    icon: Icons.business_outlined,
    breadcrumbs: <String>['nav.admin', 'settings.company'],
    columns: <ColumnSpec>[
      ColumnSpec('code', 'common.code', width: 110, emphasize: true),
      ColumnSpec('name', 'common.name', width: 240),
      ColumnSpec('name_ar', 'common.name_ar', width: 200),
      ColumnSpec('base_currency_code', 'common.currency', width: 120),
      ColumnSpec('is_active', 'common.active', type: FieldType.boolean, width: 90),
    ],
    fields: <FieldSpec>[
      FieldSpec(key: 'code', labelKey: 'common.code', required: true),
      FieldSpec(key: 'name', labelKey: 'common.name', required: true),
      FieldSpec(key: 'name_ar', labelKey: 'common.name_ar'),
      FieldSpec(key: 'legal_name', labelKey: 'settings.company', span: 2),
      FieldSpec(key: 'tax_registration_number', labelKey: 'common.reference'),
      FieldSpec(key: 'base_currency_code', labelKey: 'common.currency', type: FieldType.reference, optionsKey: 'lookup:currencies'),
      FieldSpec(key: 'admin_email', labelKey: 'login.email', helpKey: 'settings.users'),
      FieldSpec(key: 'admin_password', labelKey: 'login.password'),
      FieldSpec(key: 'admin_full_name', labelKey: 'common.name'),
    ],
    canEdit: false,
    canDelete: false,
  );
}
