import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:solar_pro/main.dart';

void main() {
  testWidgets('SolarPro starts on the home screen with the bottom navigation',
      (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: SolarProApp()));
    await tester.pump();

    final navigationBar = find.byType(NavigationBar);
    expect(navigationBar, findsOneWidget);
    for (final label in <String>[
      'العملاء',
      'المكونات',
      'التصميمات',
      'عروض الأسعار',
      'الإعدادات',
    ]) {
      // Scope the lookup to the navigation bar: the same string is also used
      // as the AppBar title of the tab that happens to be on screen.
      expect(
        find.descendant(of: navigationBar, matching: find.text(label)),
        findsOneWidget,
        reason: 'missing tab: $label',
      );
    }
  });

  testWidgets('the whole app is laid out right-to-left',
      (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: SolarProApp()));
    await tester.pump();

    // `MaterialApp` installs its own (ltr) Directionality; the app wraps
    // everything in an rtl one below it, so read the direction the home screen
    // actually inherits instead of the outermost widget.
    final direction = Directionality.of(tester.element(find.byType(NavigationBar)));
    expect(direction, TextDirection.rtl);
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
