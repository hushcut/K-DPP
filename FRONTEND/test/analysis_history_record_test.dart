import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/analysis_history_record.dart';

void main() {
  test('parses a backend analysis history record', () {
    final record = AnalysisHistoryRecord.fromJson({
      'id': 13,
      'user_id': 7,
      'materials': {'cotton': 80, 'polyester': 20.0},
      'carbon_footprint': 1.46,
      'carbon_footprint_min': 0.83,
      'carbon_footprint_max': 2.08,
      'min_weight_grams': 100,
      'max_weight_grams': 250,
      'created_at': '2026-06-04T12:00:00',
    });

    expect(record.id, 13);
    expect(record.userId, 7);
    expect(record.materials, {'cotton': 80.0, 'polyester': 20.0});
    expect(record.carbonFootprint, 1.46);
    expect(record.carbonFootprintMin, 0.83);
    expect(record.carbonFootprintMax, 2.08);
    expect(record.minWeightGram, 100);
    expect(record.maxWeightGram, 250);
    expect(record.createdAt, DateTime(2026, 6, 4, 12));
  });

  test('rejects a history record without required calculation data', () {
    expect(
      () => AnalysisHistoryRecord.fromJson({
        'id': 13,
        'materials': {'cotton': 100},
      }),
      throwsFormatException,
    );
  });
}
