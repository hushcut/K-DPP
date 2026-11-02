import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/scan_capture_service.dart';

void main() {
  group('ScanCaptureService', () {
    test('deleteTemporaryCaptureFile removes an existing temp file', () async {
      final service = ScanCaptureService();
      final tempDir = await Directory.systemTemp.createTemp(
        'scan_capture_service_test_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });

      final tempFile = File('${tempDir.path}/capture.jpg');
      await tempFile.writeAsString('temporary image');

      await service.deleteTemporaryCaptureFile(tempFile);

      expect(await tempFile.exists(), isFalse);
    });

    test('deleteTemporaryCaptureFile ignores a missing file', () async {
      final service = ScanCaptureService();
      final tempFile = File(
        '${Directory.systemTemp.path}/missing_scan_capture_file.jpg',
      );

      await service.deleteTemporaryCaptureFile(tempFile);

      expect(await tempFile.exists(), isFalse);
    });
  });
}
