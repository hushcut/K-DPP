import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/closet_screen.dart';
import 'package:k_dpp/display_settings_screen.dart';
import 'package:k_dpp/email_login_screen.dart';
import 'package:k_dpp/login_screen.dart';
import 'package:k_dpp/main_screen.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/navigation_bar_opacity_provider.dart';
import 'package:k_dpp/password_reset_screen.dart';
import 'package:k_dpp/report_screen.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/services/material_catalog_api_service.dart';
import 'package:k_dpp/services/material_catalog_controller.dart';
import 'package:k_dpp/settings_screen.dart';
import 'package:k_dpp/signup_screen.dart';
import 'package:k_dpp/theme_provider.dart';
import 'package:k_dpp/utils/clothing_type_catalog.dart';
import 'package:k_dpp/widgets/app_banner.dart';
import 'package:k_dpp/widgets/clothing_type_picker_sheet.dart';
import 'package:k_dpp/widgets/material_input_collection.dart';
import 'package:k_dpp/widgets/material_picker_sheet.dart';
import 'package:k_dpp/widgets/scan_camera_view.dart';
import 'package:k_dpp/widgets/scan_result_view.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';

// C59: 누를 수 있는 곳은 48×48 이상이어야 한다(Android 접근성 기준). 홈 '옷장 보기' 40,
// 카메라 오류의 '다시 시도'·'권한 확인 방법' 36, 스캔 결과의 소재명·함유율 칸 43 이 모자랐다.
//
// Flutter 검사(androidTapTargetGuideline)는 화면이나 스크롤 영역 가장자리에 닿은 것은 반쯤 가려졌을
// 수 있다며 건너뛴다. 카메라 오류 버튼은 작은 스크롤 영역의 가장자리에 붙어 있어 36 이어도 통과했으므로
// 크기를 따로 잰다.
void main() {
  void usePhone(WidgetTester tester) {
    tester.view.physicalSize = const Size(1170, 2532);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
  }

  /// 화면에 보이는 누를 곳을 검사하고, 스크롤할 수 있으면 끝까지 내리며 다시 검사합니다.
  Future<void> expectTapTargets(WidgetTester tester) async {
    await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
    final scrollables = find.byType(Scrollable);
    for (var i = 0; i < scrollables.evaluate().length; i++) {
      final state = tester.state<ScrollableState>(scrollables.at(i));
      if (state.position.axis != Axis.vertical) continue;
      for (var step = 0; step < 20; step++) {
        final before = state.position.pixels;
        if (before >= state.position.maxScrollExtent) break;
        state.position.jumpTo(
          (before + 300).clamp(0, state.position.maxScrollExtent),
        );
        await tester.pumpAndSettle();
        await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      }
    }
  }

  Clothes clothesWith(String title, {int health = 84}) => Clothes(
    title: title,
    category: '상의',
    health: health,
    materials: const {'cotton': 100},
    careInstruction: '찬물 세탁',
    carbonFootprint: 1.0,
  );

  Future<ClosetProvider> providerWith(List<Clothes> items) async {
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: FakeAuthSessionStorage(),
    );
    for (final item in items) {
      await provider.addClothes(item);
    }
    return provider;
  }

  Future<void> pump(
    WidgetTester tester,
    Widget home, {
    ClosetProvider? provider,
  }) async {
    final closet = provider ?? await providerWith(const []);
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: closet),
          ChangeNotifierProvider(create: (_) => ThemeProvider()),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
          ChangeNotifierProvider(create: (_) => NavigationBarOpacityProvider()),
        ],
        child: MaterialApp(builder: AppBannerHost.builder, home: home),
      ),
    );
    await tester.pumpAndSettle();
  }

  group('누를 수 있는 곳은 48×48 이상이다', () {
    testWidgets('홈', (tester) async {
      usePhone(tester);
      final semantics = tester.ensureSemantics();
      final provider = await providerWith([clothesWith('셔츠')]);
      await pump(tester, const MainScreen(), provider: provider);
      await expectTapTargets(tester);
      semantics.dispose();
    });

    testWidgets('옷장', (tester) async {
      usePhone(tester);
      final semantics = tester.ensureSemantics();
      final provider = await providerWith([
        clothesWith('셔츠'),
        clothesWith('니트', health: 10),
      ]);
      await pump(
        tester,
        Scaffold(body: ClosetScreen(onOpenReport: (_) {})),
        provider: provider,
      );
      await expectTapTargets(tester);
      await tester.tap(find.text('선택'));
      await tester.pumpAndSettle();
      await expectTapTargets(tester);
      semantics.dispose();
    });

    testWidgets('리포트', (tester) async {
      usePhone(tester);
      final semantics = tester.ensureSemantics();
      final provider = await providerWith([clothesWith('셔츠')]);
      await pump(
        tester,
        const Scaffold(body: ReportScreen()),
        provider: provider,
      );
      await expectTapTargets(tester);
      semantics.dispose();
    });

    testWidgets('설정', (tester) async {
      usePhone(tester);
      final semantics = tester.ensureSemantics();
      final provider = await providerWith(const []);
      await provider.setAuthenticatedUser(
        nickname: '홍길동',
        email: 'a@example.com',
        accessToken: 'access-token',
        expiresInSeconds: 3600,
      );
      await pump(
        tester,
        SettingsScreen(
          authApiService: AuthApiService(
            baseUrl: 'https://example.test',
            client: MockClient((_) async => http.Response('{}', 500)),
          ),
        ),
        provider: provider,
      );
      await expectTapTargets(tester);
      semantics.dispose();
    });

    testWidgets('화면 설정', (tester) async {
      usePhone(tester);
      final semantics = tester.ensureSemantics();
      await pump(tester, const DisplaySettingsScreen());
      await expectTapTargets(tester);
      semantics.dispose();
    });

    for (final (name, screen) in [
      ('로그인 첫 화면', const LoginScreen(showKakaoLogin: false) as Widget),
      ('이메일 로그인', const EmailLoginScreen()),
      ('회원가입', const SignupScreen()),
      ('비밀번호 찾기', const PasswordResetScreen()),
    ]) {
      testWidgets(name, (tester) async {
        usePhone(tester);
        final semantics = tester.ensureSemantics();
        await pump(tester, screen);
        await expectTapTargets(tester);
        semantics.dispose();
      });
    }

    for (final failed in [false, true]) {
      testWidgets('스캔 결과(${failed ? '분석 실패' : '분석 성공'})', (tester) async {
        usePhone(tester);
        final semantics = tester.ensureSemantics();
        final materialInputs = MaterialInputCollection()
          ..setFromMaterials({'cotton': 70, 'polyester': 30});
        final titleController = TextEditingController(text: '새로 스캔한 의류');
        addTearDown(materialInputs.dispose);
        addTearDown(titleController.dispose);
        await pump(
          tester,
          Scaffold(
            body: ScanResultView(
              formKey: GlobalKey<FormState>(),
              hasTriedSubmit: false,
              isSaving: false,
              isScanFailed: failed,
              titleController: titleController,
              selectedClothingType: ClothingTypeCatalog.defaultOption,
              materialInputs: materialInputs,
              scannedCare: '찬물 세탁',
              originalMaterials: const {'cotton': 70, 'polyester': 30},
              validateTitle: (_) => null,
              validateMaterialName: (_) => null,
              validateMaterialValue: (_) => null,
              onSelectClothingType: () {},
              onAddMaterial: () {},
              onRemoveMaterial: (_) {},
              onSubmit: () {},
              onReset: () {},
            ),
          ),
        );
        await expectTapTargets(tester);
        semantics.dispose();
      });
    }

    for (final message in ['카메라를 열지 못했어요.', '카메라 권한이 필요해요.']) {
      testWidgets('카메라 오류: $message', (tester) async {
        usePhone(tester);
        final semantics = tester.ensureSemantics();
        await pump(
          tester,
          Scaffold(
            body: ScanCameraView(
              cameraController: null,
              selectedImage: null,
              isScanning: false,
              isCameraInitializing: false,
              cameraErrorMessage: message,
              onRetryCamera: () {},
              onPickFromGallery: () {},
              onTakePicture: () {},
            ),
          ),
        );
        await expectTapTargets(tester);
        for (final label in ['다시 시도', if (message.contains('권한')) '권한 확인 방법']) {
          final size = tester.getSize(find.widgetWithText(TextButton, label));
          expect(size.height, greaterThanOrEqualTo(48), reason: label);
          expect(size.width, greaterThanOrEqualTo(48), reason: label);
        }
        semantics.dispose();
      });
    }

    testWidgets('의류 종류 시트', (tester) async {
      usePhone(tester);
      final semantics = tester.ensureSemantics();
      await pump(
        tester,
        Scaffold(
          body: Builder(
            builder: (context) => Center(
              child: ElevatedButton(
                onPressed: () => showClothingTypePickerSheet(
                  context: context,
                  options: ClothingTypeCatalog.options,
                  initialSelection: ClothingTypeCatalog.defaultOption,
                  discardPrompt: ClothingTypePickerDiscardPrompt.analysisResult,
                ),
                child: const Text('시트 열기'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('시트 열기'));
      await tester.pumpAndSettle();
      await expectTapTargets(tester);
      semantics.dispose();
    });

    testWidgets('소재 선택 시트', (tester) async {
      usePhone(tester);
      final semantics = tester.ensureSemantics();
      final catalog = MaterialCatalogController(
        fetchMaterials: () async => const [
          MaterialCatalogItem(
            id: 1,
            nameKo: '면',
            nameEn: 'cotton',
            aliases: [],
          ),
          MaterialCatalogItem(id: 2, nameKo: '울', nameEn: 'wool', aliases: []),
        ],
      );
      await catalog.load();
      addTearDown(catalog.dispose);
      await pump(
        tester,
        Scaffold(
          body: Builder(
            builder: (context) => Center(
              child: ElevatedButton(
                onPressed: () =>
                    showMaterialPickerSheet(context: context, catalog: catalog),
                child: const Text('시트 열기'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('시트 열기'));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      await expectTapTargets(tester);
      semantics.dispose();
    });
  });
}
