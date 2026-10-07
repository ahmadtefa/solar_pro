import 'package:flutter_test/flutter_test.dart';
import 'package:solar_pro/core/utils/arabic_text.dart';

void main() {
  group('ArabicText.join rules', () {
    test('letters that never join to the next one are detected', () {
      // ا د ذ ر ز و ة
      const nonJoining = <int>[0x0627, 0x062F, 0x0630, 0x0631, 0x0632, 0x0648, 0x0629];
      for (final codeUnit in nonJoining) {
        expect(
          ArabicText.joinsWithNext(codeUnit),
          isFalse,
          reason: 'U+${codeUnit.toRadixString(16)} must not join to the next letter',
        );
        expect(ArabicText.joinsWithPrevious(codeUnit), isTrue);
      }
    });

    test('normal letters join on both sides', () {
      // ب ح م ل ع
      const joining = <int>[0x0628, 0x062D, 0x0645, 0x0644, 0x0639];
      for (final codeUnit in joining) {
        expect(ArabicText.joinsWithNext(codeUnit), isTrue);
        expect(ArabicText.joinsWithPrevious(codeUnit), isTrue);
      }
    });

    test('non Arabic characters never join', () {
      expect(ArabicText.joinsWithNext(' '.codeUnitAt(0)), isFalse);
      expect(ArabicText.joinsWithNext('2'.codeUnitAt(0)), isFalse);
      expect(ArabicText.joinsWithNext('A'.codeUnitAt(0)), isFalse);
    });
  });

  group('ArabicText.reshape', () {
    test('uses initial / medial / final forms inside a word', () {
      // ب: isolated FE8F, final FE90, initial FE91, medial FE92
      expect(
        ArabicText.reshape('ببب').codeUnits,
        <int>[0xFE91, 0xFE92, 0xFE90],
      );
    });

    test('a single letter keeps its isolated form', () {
      expect(ArabicText.reshape('ب').codeUnits, <int>[0xFE8F]);
    });

    test('shapes a real word the way a text engine would', () {
      // م (initial FEE3) ح (medial FEA4) م (medial FEE4) د (final FEAA)
      expect(
        ArabicText.reshape('محمد').codeUnits,
        <int>[0xFEE3, 0xFEA4, 0xFEE4, 0xFEAA],
      );
    });

    test('stops the connection after ا and other non joining letters', () {
      // با: ب connects to ا (initial FE91) and ا takes its final form (FE8E)
      expect(ArabicText.reshape('با').codeUnits, <int>[0xFE91, 0xFE8E]);
      // دب: د cannot connect forward, so ب is isolated too (FEA9 + FE8F)
      expect(ArabicText.reshape('دب').codeUnits, <int>[0xFEA9, 0xFE8F]);
      // بد: ب initial (FE91) then د final (FEAA)
      expect(ArabicText.reshape('بد').codeUnits, <int>[0xFE91, 0xFEAA]);
    });

    test('uses the LAM-ALEF ligature', () {
      expect(ArabicText.reshape('لا').codeUnits, <int>[0xFEFB]);
      // علا: ع initial (FECB) + LAM-ALEF final ligature (FEFC)
      expect(ArabicText.reshape('علا').codeUnits, <int>[0xFECB, 0xFEFC]);
    });

    test('leaves digits, Latin text and spaces untouched', () {
      expect(ArabicText.reshape('2024'), '2024');
      expect(ArabicText.reshape('SolarPro'), 'SolarPro');
      final mixed = ArabicText.reshape('عدد 20 لوح');
      expect(mixed, contains('20'));
      expect(mixed, contains(' '));
    });

    test('keeps the length (except for LAM-ALEF ligatures)', () {
      for (final word in <String>['الشمس', 'محمد', 'طاقة', 'ب', 'عربى 20']) {
        final shaped = ArabicText.reshape(word);
        final ligatures = 'لا'.allMatches(word).length;
        expect(shaped.length, word.length - ligatures, reason: word);
      }
    });

    test('is idempotent - presentation forms are not re-shaped', () {
      for (final word in <String>['الشمس', 'محمد', 'لا', 'عدد 20 لوح']) {
        final once = ArabicText.reshape(word);
        expect(ArabicText.reshape(once), once, reason: word);
      }
    });

    test('handles the empty string', () {
      expect(ArabicText.reshape(''), '');
    });

    test('covers the whole Arabic block', () {
      expect(ArabicText.coveredLetters, greaterThan(60));
    });
  });
}
