import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:solar_pro/main.dart';

void main() {
  testWidgets('SolarPro starts on the home screen with the bottom navigation',
      (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: SolarProApp()));
    await tester.pump();

    expect(find.byType(NavigationBar), findsOneWidget);
    for (final label in <String>[
      'العملاء',
      'المكونات',
      'التصميمات',
      'عروض الأسعار',
      'الإعدادات',
    ]) {
      expect(find.text(label), findsOneWidget, reason: 'missing tab: $label');
    }
  });

  testWidgets('the whole app is laid out right-to-left',
      (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: SolarProApp()));
    await tester.pump();

    final directionality =
        tester.widget<Directionality>(find.byType(Directionality).first);
    expect(directionality.textDirection, TextDirection.rtl);
  });

  testWidgets('switching tabs keeps the customer list on screen',
      (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: SolarProApp()));
    await tester.pump();

    await tester.tap(find.text('عروض الأسعار'));
    await tester.pump();

    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.byType(IndexedStack), findsOneWidget);
  });
}
