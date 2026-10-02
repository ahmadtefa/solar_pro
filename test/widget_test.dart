import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:solar_pro/main.dart';

void main() {
  testWidgets('SolarPro App smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: SolarProApp()));
    
    // Wait for the splash screen to load
    await tester.pumpAndSettle();
    
    // Verify the app title is displayed
    expect(find.text('SolarPro'), findsOneWidget);
  });
}
