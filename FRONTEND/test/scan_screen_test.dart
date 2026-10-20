import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/models/scan_result.dart';
import 'package:k_dpp/scan_screen.dart';
import 'package:k_dpp/services/carbon_api_service.dart';
import 'package:k_dpp/services/scan_analysis_service.dart';
import 'package:k_dpp/services/scan_api_service.dart';
import 'package:k_dpp/services/scan_camera_session.dart';
import 'package:k_dpp/services/scan_capture_service.dart';
import 'package:k_dpp/theme/app_palette.dart';
import 'package:k_dpp/utils/clothing_type_catalog.dart';
import 'package:k_dpp/widgets/app_banner.dart';
import 'package:k_dpp/widgets/scan_camera_view.dart';
import 'package:k_dpp/widgets/scan_result_view.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';

// C11: 스캔 화면의 상태 흐름(촬영·앨범 → 분석 → 종류 선택 → 결과 입력 → 저장)을 카메라·서버 없이
// 따라간다. 분석·사진 가져오기·탄소 계산 서비스는 ScanScreen 의 테스트용 생성 함수로 갈아 끼운다.
void main() {
  // 카메라 준비 표시가 계속 돌 수 있어 settle 대신 시트·라우트 전환보다 길게 펌프한다.
  const transition = Duration(milliseconds: 1000);

  final cameraFile = File('/k-dpp-test/camera-label.jpg');
  final albumFile = File('/k-dpp-test/album-label.jpg');

  late _FakeScanAnalysisService analysis;
  late _FakeScanCaptureService capture;
  late _FakeCarbonApiService carbon;
  late ValueNotifier<bool> isActive;
  late List<Clothes> savedClothes;
  late FakeClosetStorage storage;

  setUp(() {
    analysis = _FakeScanAnalysisService();
    capture = _FakeScanCaptureService(
      cameraFile: cameraFile,
      albumFile: albumFile,
    );
    carbon = _FakeCarbonApiService();
    isActive = ValueNotifier(true);
    savedClothes = [];
    storage = FakeClosetStorage();
    ScanScreen.scanAnalysisServiceFactory = () => analysis;
    ScanScreen.scanCaptureServiceFactory = () => capture;
    ScanScreen.carbonApiServiceFactory = () => carbon;
  });

  tearDown(() {
    ScanScreen.scanAnalysisServiceFactory = ScanAnalysisService.new;
    ScanScreen.scanCaptureServiceFactory = ScanCaptureService.new;
    ScanScreen.carbonApiServiceFactory = CarbonApiService.new;
    isActive.dispose();
  });

  Future<ClosetProvider> pumpScanScreen(
    WidgetTester tester, {
    bool signedIn = false,
    bool sessionExpired = false,
  }) async {
    final provider = ClosetProvider(
      storage: storage,
      authSessionStorage: FakeAuthSessionStorage(),
    );
    if (signedIn) {
      await provider.setAuthenticatedUser(
        nickname: 'A',
        email: 'a@example.com',
        accessToken: 'token-a',
        // 0초면 만들자마자 만료된 세션이다(토큰은 남고 isAuthenticated 는 false).
        expiresInSeconds: sessionExpired ? 0 : 3600,
      );
    }

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
        ],
        child: MaterialApp(
          builder: AppBannerHost.builder,
          routes: {'/login': (_) => const Scaffold(body: Text('로그인 화면'))},
          home: Scaffold(
            body: ValueListenableBuilder<bool>(
              valueListenable: isActive,
              builder: (context, active, _) =>
                  ScanScreen(isActive: active, onSaved: savedClothes.add),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    return provider;
  }

  Future<void> tapAlbum(WidgetTester tester) async {
    await tester.tap(find.byIcon(Icons.photo_library_outlined));
    await tester.pump();
  }

  Future<void> tapShutter(WidgetTester tester) async {
    await tester.tap(find.byIcon(Icons.camera_alt));
    await tester.pump();
  }

  // 분석을 끝내고 종류 선택 시트가 다 올라올 때까지 기다린다(올라오는 도중엔 탭이 빗나간다).
  Future<void> finishAnalysis(
    WidgetTester tester,
    ScanAnalysisOutcome outcome,
  ) async {
    analysis.complete(outcome);
    await tester.pump();
    await tester.pump(transition);
  }

  Future<void> chooseType(WidgetTester tester, String label) async {
    await tester.tap(find.text(label));
    await tester.pump();
    await tester.pump(transition);
  }

  Finder sheetOption(String label) =>
      find.bySemanticsLabel(RegExp('^${RegExp.escape(label)}, '));

  String titleText(WidgetTester tester) => tester
      .widget<TextFormField>(find.widgetWithText(TextFormField, '의류 이름'))
      .controller!
      .text;

  Finder materialField(String text) => find.widgetWithText(TextFormField, text);

  // 지금 떠 있는 배너 한 장의 (글자, 종류)입니다.
  (String, AppBannerKind)? shownBanner(WidgetTester tester) {
    final views = find.byType(AppBannerView);
    if (views.evaluate().isEmpty) return null;
    final view = tester.widget<AppBannerView>(views);
    return (view.message, view.kind);
  }

  ScanResult knitResult() => ScanResult(
    materials: const {'면': 80, '폴리에스터': 20},
    careInstruction: '찬물 손세탁',
    title: '분석한 니트',
    category: 'knit',
    health: 72,
  );

  const unauthorized = ScanApiException(
    type: ScanApiErrorType.unauthorized,
    message: '',
    statusCode: 401,
  );

  group('분석 결과에 따른 흐름', () {
    testWidgets('분석이 성공하면 추론한 종류가 골라진 시트가 열리고, 고르면 분석 값으로 결과 화면이 채워진다', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      await pumpScanScreen(tester, signedIn: true);

      await tapAlbum(tester);
      expect(analysis.analyzedFiles.map((file) => file.path), [albumFile.path]);
      expect(analysis.accessTokens, ['token-a']);
      // 분석을 기다리는 동안엔 시트도 결과 화면도 없다.
      expect(find.byType(BottomSheet), findsNothing);

      await finishAnalysis(tester, ScanAnalysisSuccess(knitResult()));

      expect(find.byType(BottomSheet), findsOneWidget);
      expect(
        tester.getSemantics(sheetOption('니트')),
        isSemantics(isSelected: true),
      );
      expect(
        tester.getSemantics(sheetOption('반팔 티셔츠')),
        isSemantics(isSelected: false),
      );

      await chooseType(tester, '니트');

      expect(find.byType(ScanResultView), findsOneWidget);
      expect(find.text('스캔 완료!'), findsOneWidget);
      expect(find.text('직접 입력 모드'), findsNothing);
      expect(titleText(tester), '분석한 니트');
      expect(materialField('면'), findsOneWidget);
      expect(materialField('80'), findsOneWidget);
      expect(materialField('폴리에스터'), findsOneWidget);
      expect(materialField('20'), findsOneWidget);
      expect(find.textContaining('찬물 손세탁'), findsOneWidget);
      // 소재를 고치지 않았으니 서버 건강도를 그대로 쓴다.
      expect(find.textContaining('건강도: 72%'), findsOneWidget);
      semantics.dispose();
    });

    testWidgets('분석 성공 뒤 시트에서 "다시 촬영" 을 확인하면 결과를 버리고 촬영 화면으로 돌아가 다시 찍을 수 있다', (
      tester,
    ) async {
      await pumpScanScreen(tester);
      await tapAlbum(tester);
      await finishAnalysis(tester, ScanAnalysisSuccess(knitResult()));

      await tester.tap(
        find.descendant(
          of: find.byType(BottomSheet),
          matching: find.text('다시 촬영'),
        ),
      );
      await tester.pump();
      await tester.pump(transition);
      expect(find.text('다시 촬영하면 현재 분석 결과가 사라져요.'), findsOneWidget);

      await tester.tap(
        find.descendant(
          of: find.byType(AlertDialog),
          matching: find.text('다시 촬영'),
        ),
      );
      await tester.pump();
      await tester.pump(transition);

      expect(find.byType(BottomSheet), findsNothing);
      expect(find.byType(ScanResultView), findsNothing);
      expect(find.byType(ScanCameraView), findsOneWidget);

      // 버튼이 잠긴 채 남지 않고, 앞 분석 값이 다음 결과에 섞이지 않는다.
      await tapAlbum(tester);
      expect(analysis.analyzedFiles, hasLength(2));
      await finishAnalysis(
        tester,
        const ScanAnalysisFailure(
          ScanApiException(type: ScanApiErrorType.ocrFailed, message: ''),
        ),
      );
      await chooseType(tester, '반팔 티셔츠');

      expect(find.text('스캔 실패'), findsOneWidget);
      expect(materialField('면'), findsNothing);
      expect(find.textContaining('찬물 손세탁'), findsNothing);
      expect(titleText(tester), isNot('분석한 니트'));
    });

    testWidgets('분석이 실패하면 시트에 이유를 보이고, 고르면 서버가 보낸 부분 인식 값으로 직접 입력 화면을 채운다', (
      tester,
    ) async {
      await pumpScanScreen(tester);
      await tapAlbum(tester);

      const failure = ScanApiException(
        type: ScanApiErrorType.aiRecognitionFailed,
        message: '',
        partialMaterials: {'면': 60, '울': 40},
        careInstruction: '드라이클리닝',
        rawOcrPreview: 'COTTON 60% WOOL 40%',
      );
      await finishAnalysis(tester, const ScanAnalysisFailure(failure));

      expect(
        find.descendant(
          of: find.byType(BottomSheet),
          matching: find.text(failure.userMessage),
        ),
        findsOneWidget,
      );

      await chooseType(tester, '반팔 티셔츠');

      expect(find.text('스캔 실패'), findsOneWidget);
      expect(find.text('직접 입력 모드'), findsOneWidget);
      expect(materialField('면'), findsOneWidget);
      expect(materialField('60'), findsOneWidget);
      expect(materialField('울'), findsOneWidget);
      expect(materialField('40'), findsOneWidget);
      expect(find.textContaining('드라이클리닝'), findsOneWidget);
      expect(find.text('인식된 라벨 원문'), findsOneWidget);
      expect(find.textContaining('COTTON 60% WOOL 40%'), findsOneWidget);
      // 이유는 시트에서 이미 말했으니 배너로 다시 띄우지 않는다(DECISIONS 96).
      expect(shownBanner(tester), isNull);
    });

    testWidgets('로그인한 채 분석이 401 이면 시트 없이 로그아웃하고 로그인 화면으로 보내며 실패로 알린다', (
      tester,
    ) async {
      final provider = await pumpScanScreen(tester, signedIn: true);
      await tapAlbum(tester);
      await finishAnalysis(tester, const ScanAnalysisFailure(unauthorized));

      expect(find.byType(BottomSheet), findsNothing);
      expect(find.text('로그인 화면'), findsOneWidget);
      expect(provider.isAuthenticated, isFalse);
      expect(provider.accessToken, isNull);
      expect(shownBanner(tester), (
        unauthorized.userMessage,
        AppBannerKind.failure,
      ));
    });

    testWidgets('로그인하지 않은 채 분석이 401 이면 로그인 화면으로 보내지 않고 직접 입력 시트를 연다', (
      tester,
    ) async {
      await pumpScanScreen(tester);
      await tapAlbum(tester);
      await finishAnalysis(tester, const ScanAnalysisFailure(unauthorized));

      expect(find.text('로그인 화면'), findsNothing);
      expect(
        find.descendant(
          of: find.byType(BottomSheet),
          matching: find.text(unauthorized.userMessage),
        ),
        findsOneWidget,
      );
    });

    testWidgets('분석을 기다리는 사이 다른 화면이 위에 쌓이면 시트를 띄우지 않고 촬영 화면으로 돌아간다', (
      tester,
    ) async {
      await pumpScanScreen(tester);
      await tapAlbum(tester);

      isActive.value = false;
      await tester.pump();
      await finishAnalysis(tester, ScanAnalysisSuccess(knitResult()));
      expect(find.byType(BottomSheet), findsNothing);

      isActive.value = true;
      await tester.pump();
      expect(find.byType(ScanResultView), findsNothing);
      expect(find.byType(ScanCameraView), findsOneWidget);

      // 분석 중 잠금이 풀려 다시 고를 수 있다.
      await tapAlbum(tester);
      expect(analysis.analyzedFiles, hasLength(2));
    });
  });

  group('사진 가져오기', () {
    testWidgets('앨범에서 고르지 않고 닫으면 분석하지 않고 배너 없이 촬영 화면에 남는다', (tester) async {
      capture.galleryResult = const ScanCaptureCancelled();
      await pumpScanScreen(tester);

      await tapAlbum(tester);
      await tester.pump(transition);

      expect(capture.galleryCalls, 1);
      expect(analysis.analyzedFiles, isEmpty);
      expect(find.byType(ScanCameraView), findsOneWidget);
      expect(shownBanner(tester), isNull);

      // 앨범 잠금이 풀려 다시 열 수 있다.
      await tapAlbum(tester);
      expect(capture.galleryCalls, 2);
    });

    testWidgets('앨범을 열지 못하면 그 이유를 실패로 알리고 분석하지 않는다', (tester) async {
      capture.galleryResult = const ScanCaptureFailure(
        '사진 권한이 꺼져 있어요. 기기 설정에서 허용해 주세요.',
      );
      await pumpScanScreen(tester);

      await tapAlbum(tester);
      await tester.pump(transition);

      expect(analysis.analyzedFiles, isEmpty);
      expect(shownBanner(tester), (
        '사진 권한이 꺼져 있어요. 기기 설정에서 허용해 주세요.',
        AppBannerKind.failure,
      ));
    });

    testWidgets('카메라로 찍은 사진은 분석이 끝나 결과 화면에 들어간 뒤 임시 파일을 지운다', (tester) async {
      await pumpScanScreen(tester);

      await tapShutter(tester);
      expect(capture.cameraCalls, 1);
      expect(analysis.analyzedFiles.map((file) => file.path), [
        cameraFile.path,
      ]);

      await finishAnalysis(
        tester,
        const ScanAnalysisFailure(
          ScanApiException(type: ScanApiErrorType.ocrFailed, message: ''),
        ),
      );
      // 종류를 고르기 전에는 분석 흐름이 끝나지 않았다.
      expect(capture.deletedFiles, isEmpty);

      await chooseType(tester, '반팔 티셔츠');

      expect(find.byType(ScanResultView), findsOneWidget);
      expect(capture.deletedFiles.map((file) => file.path), [cameraFile.path]);
    });

    testWidgets('앨범에서 고른 사진은 사용자 파일이라 지우지 않는다', (tester) async {
      await pumpScanScreen(tester);

      await tapAlbum(tester);
      await finishAnalysis(tester, ScanAnalysisSuccess(knitResult()));
      await chooseType(tester, '니트');

      expect(find.byType(ScanResultView), findsOneWidget);
      expect(capture.deletedFiles, isEmpty);
    });

    testWidgets('카메라가 아직 준비되지 않았으면 기다리라고 안내하고 분석하지 않는다', (tester) async {
      capture.cameraResult = const ScanCaptureBlocked(
        '카메라를 준비하고 있어요. 잠시 후 다시 시도해 주세요.',
      );
      await pumpScanScreen(tester);

      await tapShutter(tester);
      await tester.pump(transition);

      expect(analysis.analyzedFiles, isEmpty);
      expect(shownBanner(tester), (
        '카메라를 준비하고 있어요. 잠시 후 다시 시도해 주세요.',
        AppBannerKind.info,
      ));
    });

    testWidgets('촬영에 실패하면 실패로 알리고 분석하지 않는다', (tester) async {
      capture.cameraResult = const ScanCaptureFailure(
        '사진을 촬영하지 못했어요. 다시 시도해 주세요.',
      );
      await pumpScanScreen(tester);

      await tapShutter(tester);
      await tester.pump(transition);

      expect(analysis.analyzedFiles, isEmpty);
      expect(shownBanner(tester), (
        '사진을 촬영하지 못했어요. 다시 시도해 주세요.',
        AppBannerKind.failure,
      ));
    });
  });

  group('결과 저장', () {
    Future<void> openKnitResult(WidgetTester tester) async {
      await tapAlbum(tester);
      await finishAnalysis(tester, ScanAnalysisSuccess(knitResult()));
      await chooseType(tester, '니트');
      expect(find.byType(ScanResultView), findsOneWidget);
    }

    Future<void> tapSave(WidgetTester tester) async {
      await tester.ensureVisible(find.text('옷장에 저장하기'));
      await tester.tap(find.text('옷장에 저장하기'));
      await tester.pump();
      await tester.pump(transition);
    }

    testWidgets(
      '로그인했으면 고친 소재와 고른 종류의 무게 범위로 서버 계산을 받아 그 값으로 저장하고 촬영 화면으로 돌아간다',
      (tester) async {
        final provider = await pumpScanScreen(tester, signedIn: true);
        await openKnitResult(tester);

        await tapSave(tester);

        expect(carbon.calls, hasLength(1));
        final call = carbon.calls.single;
        expect(call.materials, {'면': 80.0, '폴리에스터': 20.0});
        expect(call.accessToken, 'token-a');
        // 고른 니트의 무게 범위다(앱 내장 표 — 테스트에선 서버 무게표를 받지 못한다).
        final knit = ClothingTypeCatalog.inferFromCategory('knit');
        expect(knit.label, '니트');
        expect(
          knit.minWeightGram,
          isNot(ClothingTypeCatalog.defaultOption.minWeightGram),
        );
        expect(call.minWeightGram, knit.minWeightGram);
        expect(call.maxWeightGram, knit.maxWeightGram);

        final saved = savedClothes.single;
        expect(saved.title, '분석한 니트');
        expect(saved.carbonFootprintSource, CarbonFootprintSource.server);
        expect(saved.carbonFootprint, 1.5);
        expect(saved.savedResultId, 4242);
        expect(saved.minWeightGram, call.minWeightGram);
        expect(saved.maxWeightGram, call.maxWeightGram);
        expect(provider.items.single.savedResultId, 4242);

        expect(find.byType(ScanResultView), findsNothing);
        expect(find.byType(ScanCameraView), findsOneWidget);
        expect(shownBanner(tester), isNull);
      },
    );

    testWidgets('서버 계산이 401 이 아닌 이유로 실패하면 임시 추정값으로 저장하고 그렇게 했다고 안내한다', (
      tester,
    ) async {
      carbon.failWith = CarbonApiErrorType.server;
      final provider = await pumpScanScreen(tester, signedIn: true);
      await openKnitResult(tester);

      await tapSave(tester);

      expect(carbon.calls, hasLength(1));
      final saved = savedClothes.single;
      expect(saved.carbonFootprintSource, CarbonFootprintSource.localEstimate);
      expect(saved.savedResultId, isNull);
      expect(provider.items, hasLength(1));
      expect(shownBanner(tester), ('탄소량은 임시 추정값으로 저장했어요.', AppBannerKind.info));
      expect(find.byType(ScanCameraView), findsOneWidget);
    });

    testWidgets('로그인하지 않았으면 서버 계산 없이 기기에서 추정한 값으로 저장한다', (tester) async {
      final provider = await pumpScanScreen(tester);
      await openKnitResult(tester);

      await tapSave(tester);

      expect(carbon.calls, isEmpty);
      expect(
        savedClothes.single.carbonFootprintSource,
        CarbonFootprintSource.localEstimate,
      );
      expect(provider.items, hasLength(1));
      expect(shownBanner(tester), isNull);
    });

    testWidgets('세션이 이미 만료됐으면 서버 계산 없이 기기에 저장하고 로그인 화면으로 보내며 리포트는 열지 않는다', (
      tester,
    ) async {
      await pumpScanScreen(tester, signedIn: true, sessionExpired: true);
      await openKnitResult(tester);

      await tapSave(tester);

      expect(carbon.calls, isEmpty);
      expect(savedClothes, isEmpty);
      expect(
        (await storage.loadClothesListOrNullFor(
          'a@example.com',
        ))?.map((item) => item.title),
        ['분석한 니트'],
      );
      expect(find.text('로그인 화면'), findsOneWidget);
      expect(shownBanner(tester), (
        '로그인이 만료됐어요. 의류는 기기에 저장했어요.',
        AppBannerKind.info,
      ));
    });

    testWidgets('같은 계정인데 서버 계산이 401 이면 기기에 저장하고 로그인 화면으로 보내며 리포트는 열지 않는다', (
      tester,
    ) async {
      carbon.failWith = CarbonApiErrorType.unauthorized;
      await pumpScanScreen(tester, signedIn: true);
      await openKnitResult(tester);

      await tapSave(tester);

      expect(carbon.calls, hasLength(1));
      expect(savedClothes, isEmpty);
      expect(
        (await storage.loadClothesListOrNullFor(
          'a@example.com',
        ))?.map((item) => item.carbonFootprintSource),
        [CarbonFootprintSource.localEstimate],
      );
      expect(find.text('로그인 화면'), findsOneWidget);
      expect(shownBanner(tester), (
        '로그인이 만료됐어요. 의류는 기기에 저장했어요.',
        AppBannerKind.info,
      ));
    });

    // AI 연동 협의안 R1: 서버가 계산할 수 없는 입력이라고 거절(400/422)하면 근거 없는 임시값으로
    // 저장하지 않고, 입력을 그대로 둔 채 고치거나 다시 찍게 한다. 거절 본문은 서버 오류 처리
    // (BACKEND main.py)가 보내는 모양 그대로다. 정상 계산(200)은 위 첫 시험이 본다.
    group('계산 입력 거절(400/422)만 저장을 멈춘다 — AI 연동 협의안 R1', () {
      const _ServerRejection materialNotFound = (
        statusCode: 400,
        body: {
          'status': 'error',
          'error_code': 'MATERIAL_NOT_FOUND',
          'message': '등록되지 않은 소재가 있습니다.',
          'detail': {
            'error_code': 'MATERIAL_NOT_FOUND',
            'message': '등록되지 않은 소재가 있습니다.',
            'unknown_materials': ['아세테이트'],
          },
        },
      );

      ScanResult acetateResult() => ScanResult(
        materials: const {'아세테이트': 60, '면': 40},
        careInstruction: '드라이클리닝',
        title: '분석한 블라우스',
        category: 'knit',
        health: 70,
      );

      Future<void> openAcetateResult(WidgetTester tester) async {
        await tapAlbum(tester);
        await finishAnalysis(tester, ScanAnalysisSuccess(acetateResult()));
        await chooseType(tester, '니트');
        expect(find.byType(ScanResultView), findsOneWidget);
      }

      // 옷장에도 저장 완료 콜백(리포트 열기)에도 가지 않고, 저장 중 표시가 풀린 결과 화면에 남는다.
      Future<void> expectNotSavedAndEditable(
        WidgetTester tester,
        ClosetProvider provider,
      ) async {
        expect(savedClothes, isEmpty);
        expect(provider.items, isEmpty);
        expect(
          (await storage.loadClothesListOrNullFor('a@example.com')) ??
              const <Clothes>[],
          isEmpty,
        );
        expect(find.byType(ScanResultView), findsOneWidget);
        expect(find.byType(ScanCameraView), findsNothing);
        expect(find.textContaining('저장했어요'), findsNothing);
        // 저장 중이면 버튼 글자 대신 도는 표시가 들어가 이 버튼을 찾지 못한다.
        expect(
          tester
              .widget<ElevatedButton>(
                find.widgetWithText(ElevatedButton, '옷장에 저장하기'),
              )
              .onPressed,
          isNotNull,
        );
      }

      testWidgets(
        '400 MATERIAL_NOT_FOUND 면 옷장에 넣지 않고 리포트도 열지 않으며, 입력과 소재명을 둔 채 기준이 없다고 알린다',
        (tester) async {
          carbon.rejectWith = materialNotFound;
          final provider = await pumpScanScreen(tester, signedIn: true);
          await openAcetateResult(tester);

          await tapSave(tester);

          expect(carbon.calls, hasLength(1));
          await expectNotSavedAndEditable(tester, provider);
          expect(titleText(tester), '분석한 블라우스');
          expect(materialField('아세테이트'), findsOneWidget);
          expect(materialField('60'), findsOneWidget);
          expect(materialField('면'), findsOneWidget);
          expect(materialField('40'), findsOneWidget);
          expect(
            tester.widget<TextFormField>(materialField('아세테이트')).enabled,
            isTrue,
          );
          expect(shownBanner(tester), (
            '아세테이트 소재는 탄소 계산 기준이 없어 저장하지 못했어요.',
            AppBannerKind.failure,
          ));
        },
      );

      testWidgets(
        '400 이 소재 비율 같은 다른 입력 거절이면 저장하지 않고, 저장했다는 말 없이 혼용률을 확인하라고 알린다',
        (tester) async {
          carbon.rejectWith = (
            statusCode: 400,
            body: {
              'status': 'error',
              'error_code': 'MATERIAL_RATIO_INVALID',
              'message': '계산 입력 또는 계수 설정을 확인해 주세요.',
              'detail': {
                'error_code': 'MATERIAL_RATIO_INVALID',
                'message': '계산 입력 또는 계수 설정을 확인해 주세요.',
              },
            },
          );
          final provider = await pumpScanScreen(tester, signedIn: true);
          await openKnitResult(tester);

          await tapSave(tester);

          expect(carbon.calls, hasLength(1));
          await expectNotSavedAndEditable(tester, provider);
          expect(titleText(tester), '분석한 니트');
          expect(materialField('80'), findsOneWidget);
          expect(materialField('20'), findsOneWidget);
          expect(shownBanner(tester), (
            '탄소량을 계산할 수 없어 저장하지 못했어요. 소재와 혼용률을 확인해 주세요.',
            AppBannerKind.failure,
          ));
        },
      );

      testWidgets('422 VALIDATION_ERROR 면 저장하지 않고 입력을 둔 채 저장 중 표시를 푼다', (
        tester,
      ) async {
        carbon.rejectWith = (
          statusCode: 422,
          body: {
            'status': 'error',
            'error_code': 'VALIDATION_ERROR',
            'message': '요청 형식이 올바르지 않습니다.',
            'detail': [
              {
                'loc': ['body', 'materials', '면'],
                'msg': 'Input should be a valid number',
                'type': 'float_parsing',
              },
            ],
          },
        );
        final provider = await pumpScanScreen(tester, signedIn: true);
        await openKnitResult(tester);

        await tapSave(tester);

        expect(carbon.calls, hasLength(1));
        await expectNotSavedAndEditable(tester, provider);
        expect(titleText(tester), '분석한 니트');
        expect(materialField('면'), findsOneWidget);
        expect(find.bySemanticsLabel('의류 저장 중'), findsNothing);
        expect(shownBanner(tester)?.$2, AppBannerKind.failure);
      });

      testWidgets('거절된 뒤 소재를 고쳐 다시 누르면 새 입력으로 계산을 다시 받고, 성공하면 한 번만 저장한다', (
        tester,
      ) async {
        carbon.rejectWith = materialNotFound;
        final provider = await pumpScanScreen(tester, signedIn: true);
        await openAcetateResult(tester);
        await tapSave(tester);
        expect(provider.items, isEmpty);

        carbon.rejectWith = null;
        await tester.enterText(materialField('아세테이트'), '폴리에스터');
        await tester.pump();
        await tapSave(tester);

        expect(carbon.calls.map((call) => call.materials), [
          {'아세테이트': 60.0, '면': 40.0},
          {'폴리에스터': 60.0, '면': 40.0},
        ]);
        final saved = savedClothes.single;
        expect(saved.materials, {'폴리에스터': 60.0, '면': 40.0});
        expect(saved.carbonFootprintSource, CarbonFootprintSource.server);
        expect(saved.savedResultId, 4242);
        expect(provider.items.single.savedResultId, 4242);
        expect(find.byType(ScanCameraView), findsOneWidget);
      });

      // 입력 거절이 아닌 실패는 전처럼 임시 추정값으로 저장한다. 401·서버 오류·세션 만료는 위 시험들이 본다.
      for (final (type, message) in [
        (CarbonApiErrorType.network, '인터넷에 연결할 수 없어 임시 추정값으로 저장했어요.'),
        (CarbonApiErrorType.timeout, '탄소량은 임시 추정값으로 저장했어요.'),
        (CarbonApiErrorType.forbidden, '탄소량은 임시 추정값으로 저장했어요.'),
        (CarbonApiErrorType.invalidResponse, '탄소량은 임시 추정값으로 저장했어요.'),
        (CarbonApiErrorType.unknown, '탄소량은 임시 추정값으로 저장했어요.'),
      ]) {
        testWidgets('계산이 ${type.name} 로 실패하면 입력 거절이 아니므로 전처럼 임시 추정값으로 저장한다', (
          tester,
        ) async {
          carbon.failWith = type;
          final provider = await pumpScanScreen(tester, signedIn: true);
          await openKnitResult(tester);

          await tapSave(tester);

          expect(carbon.calls, hasLength(1));
          expect(
            savedClothes.single.carbonFootprintSource,
            CarbonFootprintSource.localEstimate,
          );
          expect(provider.items, hasLength(1));
          expect(shownBanner(tester), (message, AppBannerKind.info));
        });
      }

      // 비로그인 저장은 R1 범위 밖이다(서버 계산을 거치지 않음 — 사용자 2026-10-20).
      testWidgets('로그인하지 않았으면 미지원 소재도 서버에 묻지 않고 전처럼 기기 추정값으로 저장한다', (
        tester,
      ) async {
        carbon.rejectWith = materialNotFound;
        final provider = await pumpScanScreen(tester);
        await openAcetateResult(tester);

        await tapSave(tester);

        expect(carbon.calls, isEmpty);
        expect(
          savedClothes.single.carbonFootprintSource,
          CarbonFootprintSource.localEstimate,
        );
        expect(provider.items, hasLength(1));
      });
    });
  });

  // C53·C54: 라이트 모드에서 흰 바탕 대비 4.5:1 에 못 미치던 green·redAccent 글자와 버튼 바탕.
  testWidgets('소재 합계 글자는 맞으면 좋음, 틀리면 경고 글자색이고, 고친 결과를 버리는 확인 버튼은 경고 바탕이다', (
    tester,
  ) async {
    await pumpScanScreen(tester);
    await tapAlbum(tester);
    await finishAnalysis(tester, ScanAnalysisSuccess(knitResult()));
    await chooseType(tester, '니트');

    Color? totalColor() => tester
        .renderObject<RenderParagraph>(find.textContaining('현재 소재 합계'))
        .text
        .style
        ?.color;

    expect(totalColor(), AppPalette.light.successText);

    await tester.enterText(materialField('20'), '10');
    await tester.pump();
    expect(totalColor(), AppPalette.light.dangerText);

    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    final retake = find.descendant(
      of: find.byType(ScanResultView),
      matching: find.text('다시 촬영'),
    );
    await tester.ensureVisible(retake);
    await tester.pump();
    await tester.tap(retake);
    await tester.pump();
    await tester.pump(transition);

    final confirm = find.descendant(
      of: find.byType(AlertDialog),
      matching: find.widgetWithText(ElevatedButton, '다시 촬영'),
    );
    expect(
      tester
          .widget<ElevatedButton>(confirm)
          .style
          ?.backgroundColor
          ?.resolve(<WidgetState>{}),
      AppPalette.danger,
    );
  });
}

/// 분석 요청을 붙잡아 두었다가 테스트가 [complete] 로 정한 결과로 끝내는 분석 서비스입니다.
class _FakeScanAnalysisService extends ScanAnalysisService {
  final List<File> analyzedFiles = [];
  final List<String?> accessTokens = [];
  Completer<ScanAnalysisOutcome>? _pending;

  void complete(ScanAnalysisOutcome outcome) {
    final pending = _pending!;
    _pending = null;
    pending.complete(outcome);
  }

  @override
  Future<ScanAnalysisOutcome> analyzeLabel({
    required File imageFile,
    String? accessToken,
  }) {
    analyzedFiles.add(imageFile);
    accessTokens.add(accessToken);
    final pending = Completer<ScanAnalysisOutcome>();
    _pending = pending;
    return pending.future;
  }
}

/// 카메라·앨범 없이 테스트가 정한 결과를 돌려주고, 지운 임시 파일을 기록하는 서비스입니다.
class _FakeScanCaptureService extends ScanCaptureService {
  _FakeScanCaptureService({required File cameraFile, required File albumFile})
    : cameraResult = ScanCaptureSelected(
        imageFile: cameraFile,
        shouldDeleteAfterAnalysis: true,
      ),
      galleryResult = ScanCaptureSelected(
        imageFile: albumFile,
        shouldDeleteAfterAnalysis: false,
      );

  ScanCaptureResult cameraResult;
  ScanCaptureResult galleryResult;
  int cameraCalls = 0;
  int galleryCalls = 0;
  final List<File> deletedFiles = [];

  @override
  Future<ScanCaptureResult> captureFromCamera({
    required ScanCameraSession cameraSession,
  }) async {
    cameraCalls++;
    return cameraResult;
  }

  @override
  Future<ScanCaptureResult> pickFromGallery() async {
    galleryCalls++;
    return galleryResult;
  }

  @override
  Future<void> deleteTemporaryCaptureFile(File imageFile) async {
    deletedFiles.add(imageFile);
  }
}

/// 서버가 계산 요청을 거절할 때 돌려주는 상태 코드와 본문입니다.
typedef _ServerRejection = ({int statusCode, Map<String, Object?> body});

/// 받은 요청을 기록하고 정해 둔 계산값을 돌려주거나 [failWith] 오류로 실패하는 탄소 계산 서비스입니다.
/// [rejectWith] 를 정하면 서버 오류 본문을 실제 서비스와 같은 변환으로 예외로 바꿔 던집니다.
class _FakeCarbonApiService extends CarbonApiService {
  final List<
    ({
      Map<String, double> materials,
      double minWeightGram,
      double maxWeightGram,
      String accessToken,
    })
  >
  calls = [];
  CarbonApiErrorType? failWith;
  _ServerRejection? rejectWith;

  @override
  Future<CarbonCalculationResult> calculate({
    required Map<String, double> materials,
    required double minWeightGram,
    required double maxWeightGram,
    required String accessToken,
  }) async {
    calls.add((
      materials: materials,
      minWeightGram: minWeightGram,
      maxWeightGram: maxWeightGram,
      accessToken: accessToken,
    ));
    final rejection = rejectWith;
    if (rejection != null) {
      throw CarbonApiException.fromStatusCode(
        statusCode: rejection.statusCode,
        responseBody: jsonEncode(rejection.body),
      );
    }
    final type = failWith;
    if (type != null) {
      throw CarbonApiException(type: type, message: '');
    }
    return CarbonCalculationResult(
      carbonFactor: 8.3,
      carbonFootprint: 1.5,
      carbonFootprintMin: 0.8,
      carbonFootprintMax: 2.1,
      minWeightGram: minWeightGram,
      maxWeightGram: maxWeightGram,
      unit: 'kg CO2eq',
      savedResultId: 4242,
    );
  }
}
