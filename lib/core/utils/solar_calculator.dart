/// Solar energy calculation utilities for solar project management.
class SolarCalculator {
  SolarCalculator._();

  /// Converts horsepower (HP) to kilowatts (kW).
  ///
  /// [hp] - Power in horsepower.
  /// Returns power in kilowatts.
  static double hpToKw(double hp) => hp * 0.746;

  /// Converts kilowatts (kW) to horsepower (HP).
  ///
  /// [kw] - Power in kilowatts.
  /// Returns power in horsepower.
  static double kwToHp(double kw) => kw / 0.746;

  /// Calculates the total number of solar panels needed.
  ///
  /// [capacityW] - Total system capacity in watts.
  /// [panelPowerW] - Power rating of a single panel in watts.
  /// Returns the number of panels required (rounded up).
  static int calculateTotalPanels(double capacityW, double panelPowerW) {
    if (panelPowerW <= 0) return 0;
    return (capacityW / panelPowerW).ceil();
  }

  /// Calculates the maximum number of panels that can be connected in series per string.
  ///
  /// [inverterMaxDcVoltage] - Maximum DC input voltage of the inverter.
  /// [panelVocV] - Open-circuit voltage (Voc) of a single panel.
  /// Returns the maximum panels per string (rounded down for safety).
  static int calculateMaxPanelsPerString(double inverterMaxDcVoltage, double panelVocV) {
    if (panelVocV <= 0) return 0;
    return (inverterMaxDcVoltage / panelVocV).floor();
  }

  /// Calculates the number of strings needed for the solar array.
  ///
  /// [totalPanels] - Total number of panels in the system.
  /// [maxPanelsPerString] - Maximum panels allowed per string.
  /// Returns the number of strings required (rounded up).
  static int calculateNumberOfStrings(int totalPanels, int maxPanelsPerString) {
    if (maxPanelsPerString <= 0) return 0;
    return (totalPanels / maxPanelsPerString).ceil();
  }

  /// Distributes panels evenly across strings.
  ///
  /// [totalPanels] - Total number of panels to distribute.
  /// [numberOfStrings] - Number of strings to distribute panels across.
  /// Returns a list where each element represents panels in that string.
  /// First strings get extra panels if total is not evenly divisible.
  static List<int> distributePanelsInStrings(int totalPanels, int numberOfStrings) {
    if (numberOfStrings <= 0 || totalPanels <= 0) return [];
    
    final distribution = <int>[];
    final basePanelsPerString = totalPanels ~/ numberOfStrings;
    final extraPanels = totalPanels % numberOfStrings;
    
    for (int i = 0; i < numberOfStrings; i++) {
      // First 'extraPanels' strings get one extra panel
      final panelsInThisString = basePanelsPerString + (i < extraPanels ? 1 : 0);
      distribution.add(panelsInThisString);
    }
    
    return distribution;
  }

  /// Calculates the selling price for a solar system.
  ///
  /// [capacityKw] - System capacity in kilowatts.
  /// [pricePerKw] - Price per kilowatt.
  /// Returns the total selling price.
  static double calculateSellPrice(double capacityKw, double pricePerKw) {
    return capacityKw * pricePerKw;
  }

  /// Calculates the actual total cost of a project.
  ///
  /// [components] - Cost of components/materials.
  /// [labor] - Cost of labor/installation.
  /// [transport] - Cost of transportation/logistics.
  /// Returns the total actual cost.
  static double calculateActualCost(double components, double labor, double transport) {
    return components + labor + transport;
  }

  /// Calculates the profit from a project.
  ///
  /// [sellPrice] - Total selling price/revenue.
  /// [actualCost] - Total actual cost.
  /// Returns the profit (positive) or loss (negative).
  static double calculateProfit(double sellPrice, double actualCost) {
    return sellPrice - actualCost;
  }

  /// Calculates daily energy consumption from a list of appliances.
  ///
  /// [appliances] - List of appliances, each with:
  ///   - powerW: Power consumption in watts
  ///   - quantity: Number of units
  ///   - hoursPerDay: Hours of usage per day
  /// Returns total daily consumption in watt-hours (Wh).
  static double calculateDailyConsumption(List<Map<String, dynamic>> appliances) {
    double totalWh = 0;
    
    for (final appliance in appliances) {
      final powerW = (appliance['powerW'] as num?)?.toDouble() ?? 0;
      final quantity = (appliance['quantity'] as num?)?.toInt() ?? 1;
      final hoursPerDay = (appliance['hoursPerDay'] as num?)?.toDouble() ?? 0;
      
      totalWh += powerW * quantity * hoursPerDay;
    }
    
    return totalWh;
  }

  /// Suggests the required solar system capacity in kW.
  ///
  /// [dailyWh] - Daily energy consumption in watt-hours.
  /// [psh] - Peak sun hours at the location.
  /// [systemLossFactor] - System loss factor (default 1.3 for 30% losses).
  /// Returns suggested capacity in kW, rounded UP to nearest 0.5 kW.
  static double suggestCapacityKw(double dailyWh, double psh, {double systemLossFactor = 1.3}) {
    if (psh <= 0) return 0;
    
    // Calculate raw capacity needed in kW
    final rawCapacityKw = (dailyWh * systemLossFactor) / (psh * 1000);
    
    // Round up to nearest 0.5 kW
    return (rawCapacityKw * 2).ceil() / 2;
  }
}
