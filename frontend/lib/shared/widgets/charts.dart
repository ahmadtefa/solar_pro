import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

/// Minimal fl_chart wrappers so the rest of the app never touches chart APIs.
class SimpleLineChart extends StatelessWidget {
  const SimpleLineChart({required this.labels, required this.values, this.height = 220, super.key});

  final List<String> labels;
  final List<num> values;
  final double height;

  @override
  Widget build(BuildContext context) {
    if (values.isEmpty) {
      return SizedBox(height: height, child: const Center(child: Text('—')));
    }
    final Color color = Theme.of(context).colorScheme.primary;
    return SizedBox(
      height: height,
      child: LineChart(
        LineChartData(
          gridData: const FlGridData(show: true, drawVerticalLine: false),
          borderData: FlBorderData(show: false),
          titlesData: const FlTitlesData(show: false),
          lineTouchData: const LineTouchData(enabled: true),
          lineBarsData: <LineChartBarData>[
            LineChartBarData(
              spots: <FlSpot>[
                for (int index = 0; index < values.length; index++)
                  FlSpot(index.toDouble(), values[index].toDouble()),
              ],
              isCurved: true,
              color: color,
              barWidth: 3,
              dotData: const FlDotData(show: false),
              belowBarData: BarAreaData(show: true, color: color.withValues(alpha: 0.12)),
            ),
          ],
          minY: 0,
        ),
      ),
    );
  }
}

class SimpleBarChart extends StatelessWidget {
  const SimpleBarChart({required this.labels, required this.values, this.height = 220, super.key});

  final List<String> labels;
  final List<num> values;
  final double height;

  @override
  Widget build(BuildContext context) {
    if (values.isEmpty) {
      return SizedBox(height: height, child: const Center(child: Text('—')));
    }
    final Color color = Theme.of(context).colorScheme.primary;
    return SizedBox(
      height: height,
      child: BarChart(
        BarChartData(
          gridData: const FlGridData(show: true, drawVerticalLine: false),
          borderData: FlBorderData(show: false),
          titlesData: FlTitlesData(
            leftTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 46,
                getTitlesWidget: (double value, TitleMeta meta) {
                  final int index = value.toInt();
                  if (index < 0 || index >= labels.length) return const SizedBox.shrink();
                  final String label = labels[index];
                  return Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                      label.length > 10 ? '${label.substring(0, 9)}…' : label,
                      style: const TextStyle(fontSize: 9),
                    ),
                  );
                },
              ),
            ),
          ),
          barTouchData: BarTouchData(
            touchTooltipData: BarTouchTooltipData(
              getTooltipItem: (BarChartGroupData group, int groupIndex, BarChartRodData rod, int rodIndex) {
                final String label = groupIndex < labels.length ? labels[groupIndex] : '';
                return BarTooltipItem('$label\n${rod.toY}', const TextStyle(color: Colors.white, fontSize: 11));
              },
            ),
          ),
          barGroups: <BarChartGroupData>[
            for (int index = 0; index < values.length; index++)
              BarChartGroupData(
                x: index,
                barRods: <BarChartRodData>[
                  BarChartRodData(
                    toY: values[index].toDouble(),
                    color: color,
                    width: 16,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}
