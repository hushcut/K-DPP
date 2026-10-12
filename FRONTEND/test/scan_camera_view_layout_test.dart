import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/widgets/scan_camera_view.dart';

/// 카메라 화면은 남는 높이를 위 2 : 아래 3으로 나눠 촬영 UI를 가운데보다 위에 둔다.
///
/// 이전 3 : 1은 남는 높이가 큰 iPhone 16 Pro Max에서 촬영 버튼이 지나치게 아래로
/// 내려갔고, 3 : 2는 달라진 것을 못 느꼈다(2026-09-23 폰 확인 2회). 기종별 숫자 대신
/// 비율이므로 어느 높이에서든 같은 비율이어야 한다.
void main() {
  Future<void> pumpAtHeight(WidgetTester tester, double height) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Align(
            alignment: Alignment.topCenter,
            child: SizedBox(
              height: height,
              child: ScanCameraView(
                cameraController: null,
                selectedImage: null,
                isScanning: false,
                isCameraInitializing: false,
                cameraErrorMessage: null,
                onRetryCamera: () {},
                onPickFromGallery: () {},
                onTakePicture: () {},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  // 위·아래 여백: 안내 문구 위(상단 패딩 20 제외)와 앨범 버튼 아래(하단 패딩 20 제외)입니다.
  ({double top, double bottom}) gapsOf(WidgetTester tester, double height) {
    const contentPadding = 20.0;
    final guideTop = tester
        .getTopLeft(find.text('케어 라벨을 프레임 안에 맞춰 촬영해 주세요'))
        .dy;
    final albumBottom = tester
        .getBottomLeft(find.bySemanticsLabel('앨범에서 라벨 사진 선택'))
        .dy;

    return (
      top: guideTop - contentPadding,
      bottom: (height - contentPadding) - albumBottom,
    );
  }

  testWidgets('iPhone 16 Pro Max 높이(807)에서 남는 높이를 위 2 : 아래 3으로 나눈다', (
    tester,
  ) async {
    // 956 - 상태 표시줄 59 - 앱바 56 - 홈 표시기 34 = 807 (스캔 탭은 내비 바가 없다).
    tester.view.physicalSize = const Size(440 * 3, 807 * 3);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);

    await pumpAtHeight(tester, 807);
    final gaps = gapsOf(tester, 807);

    expect(gaps.top, greaterThan(0));
    expect(gaps.bottom, greaterThan(0));
    expect(gaps.top / gaps.bottom, closeTo(2 / 3, 0.02));
    // 이전 배치(3 : 1, 3 : 2)보다 위로 올라왔는지: 아래 여백이 전체 남는 높이의 60%다.
    expect(gaps.bottom / (gaps.top + gaps.bottom), closeTo(0.6, 0.01));
  });

  testWidgets('SM-N986N 높이(694)에서도 같은 비율이다', (tester) async {
    tester.view.physicalSize = const Size(1080, 2316);
    tester.view.devicePixelRatio = 2.8125;
    addTearDown(tester.view.reset);

    await pumpAtHeight(tester, 694);
    final gaps = gapsOf(tester, 694);

    expect(gaps.top / gaps.bottom, closeTo(2 / 3, 0.02));
  });
}
