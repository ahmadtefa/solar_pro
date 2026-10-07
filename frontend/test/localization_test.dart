import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kayan_erp/core/l10n/app_strings.dart';

void main() {
  group('localisation catalogue', () {
    test('English and Arabic expose exactly the same keys', () {
      final Set<String> english = AppStrings.keysFor('en');
      final Set<String> arabic = AppStrings.keysFor('ar');
      expect(english.length, greaterThan(200));
      expect(arabic.difference(english), isEmpty, reason: 'Arabic has keys missing in English');
      expect(english.difference(arabic), isEmpty, reason: 'English keys are missing in Arabic');
    });

    test('no value is empty and placeholders match across languages', () {
      for (final MapEntry<String, String> entry in AppStrings.valuesFor('en').entries) {
        final String arabic = AppStrings.valuesFor('ar')[entry.key] ?? '';
        expect(entry.value.trim(), isNotEmpty, reason: 'empty English value for ${entry.key}');
        expect(arabic.trim(), isNotEmpty, reason: 'empty Arabic value for ${entry.key}');
        expect(
          RegExp(r'\{[a-z_]+\}').allMatches(entry.value).length,
          RegExp(r'\{[a-z_]+\}').allMatches(arabic).length,
          reason: 'placeholder mismatch for ${entry.key}',
        );
      }
    });

    test('translation falls back to the key so missing labels are visible', () {
      const AppStrings strings = AppStrings(Locale('ar'));
      expect(strings.t('nav.dashboard'), 'لوحة المعلومات');
      expect(strings.t('this.key.does.not.exist'), 'this.key.does.not.exist');
    });

    test('Arabic is right-to-left and English is left-to-right', () {
      expect(const AppStrings(Locale('ar')).isRtl, isTrue);
      expect(const AppStrings(Locale('en')).isRtl, isFalse);
      expect(const AppStrings(Locale('ar')).direction, TextDirection.rtl);
    });

    test('placeholder substitution replaces every occurrence', () {
      const AppStrings strings = AppStrings(Locale('en'));
      expect(
        strings.tp('dash.welcome', <String, Object>{'name': 'Sara'}),
        contains('Sara'),
      );
    });
  });
}
