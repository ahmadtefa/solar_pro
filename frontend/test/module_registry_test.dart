import 'package:flutter_test/flutter_test.dart';
import 'package:kayan_erp/features/modules/module_registry.dart';
import 'package:kayan_erp/shared/resource/resource_config.dart';

void main() {
  group('module registry', () {
    test('every resource config is internally consistent', () {
      expect(ModuleRegistry.resources.length, greaterThan(50));
      for (final MapEntry<String, ResourceConfig> entry in ModuleRegistry.resources.entries) {
        final ResourceConfig config = entry.value;
        expect(config.path.startsWith('/'), isTrue, reason: '${entry.key} path must be absolute');
        expect(config.permissionPrefix.split('.').length, 2, reason: '${entry.key} needs module.entity');
        expect(config.columns, isNotEmpty, reason: '${entry.key} renders no columns');
        if (config.canCreate) {
          expect(config.fields, isNotEmpty, reason: '${entry.key} cannot create without fields');
        }
        final Set<String> fieldKeys = config.fields.map((FieldSpec field) => field.key).toSet();
        expect(fieldKeys.length, config.fields.length, reason: '${entry.key} has duplicate field keys');
      }
    });

    test('every document config declares columns, permissions and lifecycle', () {
      expect(ModuleRegistry.documents.length, greaterThan(20));
      for (final MapEntry<String, dynamic> entry in ModuleRegistry.documents.entries) {
        final dynamic config = entry.value;
        expect(config.path.startsWith('/'), isTrue);
        expect(config.permissionPrefix.split('.').length, 2);
        expect(config.columns, isNotEmpty);
        expect(config.headerFields, isNotEmpty);
        expect(config.statuses, isNotEmpty);
      }
    });

    test('navigation only references configs that exist and routes are unique', () {
      final Set<String> routes = <String>{};
      for (final NavGroup group in ModuleRegistry.navigation()) {
        expect(group.items, isNotEmpty, reason: '${group.labelKey} is empty');
        for (final NavItem item in group.items) {
          expect(routes.add(item.route), isTrue, reason: 'duplicate route ${item.route}');
          expect(item.permission.split('.').length, greaterThanOrEqualTo(2));
          if (item.route.startsWith('${ModuleRegistry.resourcePrefix}/')) {
            expect(ModuleRegistry.resource(item.route.split('/').last), isNotNull);
          }
          if (item.route.startsWith('${ModuleRegistry.documentPrefix}/')) {
            expect(ModuleRegistry.document(item.route.split('/').last), isNotNull);
          }
        }
      }
    });
  });
}
