import 'package:flutter_test/flutter_test.dart';
import 'package:solar_pro/core/utils/solar_calculator.dart';

void main() {
  group('SolarCalculator.power conversions', () {
    test('hpToKw and kwToHp round-trip', () {
      expect(SolarCalculator.hpToKw(1), closeTo(0.746, 1e-9));
      expect(SolarCalculator.kwToHp(0.746), closeTo(1, 1e-9));
      expect(SolarCalculator.kwToHp(SolarCalculator.hpToKw(13.41)), closeTo(13.41, 1e-9));
    });
  });

  group('SolarCalculator.calculateTotalPanels', () {
    test('rounds up so the capacity is always covered', () {
      expect(SolarCalculator.calculateTotalPanels(5000, 550), 10); // 9.09 -> 10
      expect(SolarCalculator.calculateTotalPanels(5500, 550), 10);
      expect(SolarCalculator.calculateTotalPanels(5501, 550), 11);
    });

    test('returns 0 for a zero or negative panel power', () {
      expect(SolarCalculator.calculateTotalPanels(5000, 0), 0);
      expect(SolarCalculator.calculateTotalPanels(5000, -10), 0);
    });
  });

  group('SolarCalculator.calculateMaxPanelsPerString', () {
    test('floors the ratio (never exceeds the inverter voltage)', () {
      expect(SolarCalculator.calculateMaxPanelsPerString(1000, 49.9), 20); // 20.04
      expect(SolarCalculator.calculateMaxPanelsPerString(600, 45), 13);
    });

    test('returns 0 when the panel Voc is unknown', () {
      expect(SolarCalculator.calculateMaxPanelsPerString(1000, 0), 0);
    });
  });

  group('SolarCalculator.calculateNumberOfStrings', () {
    test('rounds up', () {
      expect(SolarCalculator.calculateNumberOfStrings(20, 20), 1);
      expect(SolarCalculator.calculateNumberOfStrings(21, 20), 2);
      expect(SolarCalculator.calculateNumberOfStrings(0, 20), 0);
    });

    test('returns 0 for an invalid string size', () {
      expect(SolarCalculator.calculateNumberOfStrings(20, 0), 0);
    });
  });

  group('SolarCalculator.distributePanelsInStrings', () {
    test('spreads the extra panels over the first strings', () {
      expect(SolarCalculator.distributePanelsInStrings(21, 2), <int>[11, 10]);
      expect(SolarCalculator.distributePanelsInStrings(20, 2), <int>[10, 10]);
      expect(SolarCalculator.distributePanelsInStrings(7, 3), <int>[3, 2, 2]);
    });

    test('the distribution always adds up to the total', () {
      for (var total = 1; total <= 40; total++) {
        for (var strings = 1; strings <= 8; strings++) {
          final distribution =
              SolarCalculator.distributePanelsInStrings(total, strings);
          expect(distribution.length, strings);
          expect(
            distribution.reduce((a, b) => a + b),
            total,
            reason: 'total=$total strings=$strings',
          );
        }
      }
    });

    test('returns an empty list for invalid input', () {
      expect(SolarCalculator.distributePanelsInStrings(0, 3), isEmpty);
      expect(SolarCalculator.distributePanelsInStrings(10, 0), isEmpty);
    });
  });

  group('SolarCalculator money helpers', () {
    test('calculateSellPrice multiplies capacity by the price per kW', () {
      expect(SolarCalculator.calculateSellPrice(10, 15000), 150000);
    });

    test('calculateActualCost adds the three cost buckets', () {
      expect(SolarCalculator.calculateActualCost(100, 20, 30), 150);
    });

    test('calculateProfit is negative for a loss', () {
      expect(SolarCalculator.calculateProfit(1000, 800), 200);
      expect(SolarCalculator.calculateProfit(800, 1000), -200);
    });
  });

  group('SolarCalculator consumption and sizing', () {
    test('calculateDailyConsumption sums power x quantity x hours', () {
      final appliances = <Map<String, dynamic>>[
        {'powerW': 100, 'quantity': 4, 'hoursPerDay': 5},
        {'powerW': 1500, 'quantity': 1, 'hoursPerDay': 2},
      ];
      expect(SolarCalculator.calculateDailyConsumption(appliances), 5000);
    });

    test('calculateDailyConsumption tolerates missing values', () {
      final appliances = <Map<String, dynamic>>[
        <String, dynamic>{},
        {'powerW': 100, 'hoursPerDay': 2},
      ];
      expect(SolarCalculator.calculateDailyConsumption(appliances), 200);
    });

    test('suggestCapacityKw rounds up to the nearest 0.5 kW', () {
      // (10000 * 1.3) / (5 * 1000) = 2.6 kW -> 3.0
      expect(SolarCalculator.suggestCapacityKw(10000, 5), 3.0);
      // (1000 * 1.3) / (5 * 1000) = 0.26 kW -> 0.5
      expect(SolarCalculator.suggestCapacityKw(1000, 5), 0.5);
    });

    test('suggestCapacityKw returns 0 without sun hours', () {
      expect(SolarCalculator.suggestCapacityKw(10000, 0), 0);
    });
  });
}
