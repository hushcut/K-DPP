import 'package:flutter/gestures.dart' show kPressTimeout;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/closet_screen.dart';
import 'package:k_dpp/display_settings_screen.dart';
import 'package:k_dpp/main_screen.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/navigation_bar_opacity_provider.dart';
import 'package:k_dpp/settings_screen.dart';
import 'package:k_dpp/theme/app_palette.dart';
import 'package:k_dpp/theme/app_theme.dart';
import 'package:k_dpp/theme_provider.dart';
import 'package:k_dpp/utils/clothing_type_catalog.dart';
import 'package:k_dpp/widgets/app_back_button.dart';
import 'package:k_dpp/widgets/clothing_type_picker_sheet.dart';
import 'package:k_dpp/widgets/material_input_collection.dart';
import 'package:k_dpp/widgets/scan_camera_view.dart';
import 'package:k_dpp/widgets/scan_result_view.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';
import 'helpers/ink_visibility.dart';

// 2026-09-24 폰 확인: "<" 를 꾹 누르면 "리포트 닫기" 말풍선이 떴고, 옷장 카드·설정 칸은
// 눌러도 눌린 표시가 보이지 않았다. 사용자 요청으로 말풍선은 앱 전체에서 끄고,
// 누르는 곳은 모두 "<" 처럼 누름 효과(물결·강조)가 보이게 한다.
void main() {
  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
  });

  group('길게 누름 툴팁', () {
    testWidgets('앱 테마에서는 "<" 를 길게 눌러도 말풍선이 뜨지 않고, 낭독 이름은 남는다', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();

      for (final theme in [AppTheme.light(), AppTheme.dark()]) {
        await _pumpBackButton(tester, theme);
        await tester.longPress(find.byType(AppBackButton));
        await tester.pumpAndSettle();

        expect(find.text('리포트 닫기'), findsNothing);
        expect(
          find.semantics.byPredicate((node) => node.tooltip == '리포트 닫기'),
          findsOne,
        );
      }
      semantics.dispose();
    });

    testWidgets('대조: 툴팁 설정이 없는 기본 테마에서는 길게 누르면 말풍선이 뜬다', (tester) async {
      // 위 테스트가 '원래 안 뜨는 것'을 통과로 착각하지 않는지 확인합니다.
      await _pumpBackButton(tester, ThemeData());
      await tester.longPress(find.byType(AppBackButton));
      await tester.pumpAndSettle();

      expect(find.text('리포트 닫기'), findsOneWidget);
    });
  });

  group('누름 효과가 색 칠한 바탕에 가려지지 않는다', () {
    testWidgets('옷장 카드', (tester) async {
      final provider = ClosetProvider(
        storage: FakeClosetStorage(),
        authSessionStorage: FakeAuthSessionStorage(),
      );
      await provider.addClothes(_clothes('반팔 티셔츠', health: 88));
      await provider.addClothes(_clothes('낡은 셔츠', health: 10));

      await tester.pumpWidget(
        ChangeNotifierProvider.value(
          value: provider,
          child: MaterialApp(
            theme: AppTheme.light(),
            home: Scaffold(body: ClosetScreen(onOpenReport: (_) {})),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('반팔 티셔츠'), findsOneWidget);
      expect(findCoveredInk(tester), isEmpty);

      // 길게 눌러 선택한 카드도 선택 색 위에 효과가 보여야 합니다.
      await tester.longPress(find.text('반팔 티셔츠'));
      await tester.pumpAndSettle();
      expect(findCoveredInk(tester), isEmpty);
    });

    testWidgets('설정 칸', (tester) async {
      final provider = ClosetProvider(
        storage: FakeClosetStorage(),
        authSessionStorage: FakeAuthSessionStorage(),
      );
      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: provider),
            ChangeNotifierProvider(create: (_) => ThemeProvider()),
            ChangeNotifierProvider(
              create: (_) => MaterialNameDisplayProvider(),
            ),
          ],
          child: MaterialApp(
            theme: AppTheme.light(),
            home: const SettingsScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('화면 설정'), findsOneWidget);
      expect(findCoveredInk(tester), isEmpty);
    });

    testWidgets('화면 설정의 테마·소재 이름 선택 칸', (tester) async {
      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider(create: (_) => ThemeProvider()),
            ChangeNotifierProvider(
              create: (_) => MaterialNameDisplayProvider(),
            ),
            ChangeNotifierProvider(
              create: (_) => NavigationBarOpacityProvider(),
            ),
          ],
          child: MaterialApp(
            theme: AppTheme.light(),
            home: const DisplaySettingsScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('블랙'), findsOneWidget);
      expect(findCoveredInk(tester), isEmpty);

      // 소재 이름 칸은 아래에 있어 스크롤해야 그려집니다.
      await tester.scrollUntilVisible(
        find.text('영문'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      expect(findCoveredInk(tester), isEmpty);
    });

    testWidgets('하단 메뉴 홈·옷장과 가운데 스캔 버튼', (tester) async {
      await _pumpMainScreen(tester);

      expect(find.text('옷장'), findsOneWidget);
      expect(findCoveredInk(tester), isEmpty);
      // 스캔 버튼은 전에 GestureDetector 라 효과가 아예 없었으므로 효과가 붙었는지도 봅니다.
      expect(_inkOf(find.byIcon(Icons.camera_alt)), findsOneWidget);
    });

    testWidgets('스캔 결과의 무게 기준 칸', (tester) async {
      var selectCount = 0;
      final materialInputs = MaterialInputCollection()
        ..setFromMaterials({'cotton': 100});
      final titleController = TextEditingController(text: '반팔 티셔츠');
      addTearDown(materialInputs.dispose);
      addTearDown(titleController.dispose);

      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: Scaffold(
            body: ScanResultView(
              formKey: GlobalKey<FormState>(),
              hasTriedSubmit: false,
              isSaving: false,
              isScanFailed: false,
              titleController: titleController,
              selectedClothingType: ClothingTypeCatalog.defaultOption,
              materialInputs: materialInputs,
              scannedCare: '찬물 세탁',
              originalMaterials: const {'cotton': 100},
              validateTitle: (_) => null,
              validateMaterialName: (_) => null,
              validateMaterialValue: (_) => null,
              onSelectClothingType: () => selectCount++,
              onAddMaterial: () {},
              onRemoveMaterial: (_) {},
              onSubmit: () {},
              onReset: () {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(findCoveredInk(tester), isEmpty);

      // 효과 층을 칸 위에 겹쳤으므로 칸 한가운데를 누르면 그 층이 받아 선택창을 엽니다.
      await tester.tap(
        find.ancestor(of: find.text('무게 기준'), matching: find.byType(Stack)).first,
      );
      await tester.pump();
      expect(selectCount, 1);
    });

    testWidgets('의류 종류 시트의 항목과 직접 입력의 상의·하의 칩', (tester) async {
      _usePhoneView(tester);
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: Scaffold(
            body: ClothingTypePickerSheet(
              options: ClothingTypeCatalog.options,
              initialSelection: ClothingTypeCatalog.defaultOption,
              onSelected: (_) {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(findCoveredInk(tester), isEmpty);

      await tester.scrollUntilVisible(find.text('직접 입력'), 100);
      await tester.ensureVisible(find.text('직접 입력'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('직접 입력'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('하의'));
      await tester.pumpAndSettle();

      expect(find.text('상의'), findsOneWidget);
      expect(findCoveredInk(tester), isEmpty);
    });

    testWidgets('카메라 화면의 촬영·앨범 버튼', (tester) async {
      var pickCount = 0;
      var shootCount = 0;
      await _pumpCameraView(
        tester,
        isScanning: false,
        onPickFromGallery: () => pickCount++,
        onTakePicture: () => shootCount++,
      );

      expect(findCoveredInk(tester), isEmpty);
      // 두 버튼은 전에 GestureDetector 라 효과가 아예 없었으므로 효과가 붙었는지도 봅니다.
      expect(_inkOf(find.byIcon(Icons.camera_alt)), findsOneWidget);
      expect(_inkOf(find.byIcon(Icons.photo_library_outlined)), findsOneWidget);

      await tester.tap(find.byIcon(Icons.camera_alt));
      await tester.tap(find.byIcon(Icons.photo_library_outlined));
      await tester.pump();
      expect(shootCount, 1);
      expect(pickCount, 1);
    });

    testWidgets('카메라 화면: 분석 중에는 버튼이 눌리지 않는다(효과도 없음)', (tester) async {
      var pickCount = 0;
      var shootCount = 0;
      await _pumpCameraView(
        tester,
        isScanning: true,
        onPickFromGallery: () => pickCount++,
        onTakePicture: () => shootCount++,
      );

      final shutterInk = tester.widget<InkWell>(
        _inkOf(find.byIcon(Icons.camera_alt)),
      );
      expect(shutterInk.onTap, isNull);

      await tester.tap(find.byIcon(Icons.camera_alt), warnIfMissed: false);
      await tester.tap(
        find.byIcon(Icons.photo_library_outlined),
        warnIfMissed: false,
      );
      await tester.pump();
      expect(shootCount, 0);
      expect(pickCount, 0);
    });
  });

  // 2026-09-24 사용자 결정: 기본 회색 강조가 파랑 위에 덮여 옅은 회보라로 보였다.
  // 눌렀을 때 들어가는 느낌이 나게 강조와 물결을 모두 진한 파랑으로 바꾼다.
  group('파란 원 버튼은 누르는 동안 진한 파랑이 된다', () {
    final platforms = TargetPlatformVariant(<TargetPlatform>{
      TargetPlatform.iOS,
      TargetPlatform.android,
    });

    testWidgets('가운데 스캔 원', (tester) async {
      await _pumpMainScreen(tester);
      await _expectDarkBlueWhilePressed(tester, find.byIcon(Icons.camera_alt));
    }, variant: platforms);

    testWidgets('카메라 화면의 촬영 원', (tester) async {
      var shootCount = 0;
      await _pumpCameraView(
        tester,
        isScanning: false,
        onPickFromGallery: () {},
        onTakePicture: () => shootCount++,
      );
      await _expectDarkBlueWhilePressed(tester, find.byIcon(Icons.camera_alt));
      expect(shootCount, 0);
    }, variant: platforms);

    testWidgets('촬영 원을 짧게 탭해도 진한 파랑이 보인다', (tester) async {
      // 누름 강조는 kPressTimeout(100ms) 넘게 누르고 있어야 칠해지므로, 그보다 짧은 탭은
      // 물결이 맡습니다. 촬영 원은 짧게 탭하는 버튼이라 따로 봅니다.
      var shootCount = 0;
      await _pumpCameraView(
        tester,
        isScanning: false,
        onPickFromGallery: () {},
        onTakePicture: () => shootCount++,
      );

      await tester.tap(find.byIcon(Icons.camera_alt));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final inkLayer =
          Material.of(tester.element(find.byIcon(Icons.camera_alt)))
              as RenderObject;
      expect(inkLayer, paints..circle(color: AppPalette.accentPressed));
      expect(inkLayer, _paintsInkOnlyIn(AppPalette.accentPressed));
      expect(shootCount, 1);
    }, variant: platforms);
  });

  testWidgets('가운데 스캔 버튼은 원을 눌러도, 원 아래 글자를 눌러도 스캔 탭으로 간다', (
    tester,
  ) async {
    // 원에는 누름 효과(InkWell)를, 글자·여백에는 바깥 GestureDetector 를 두었으므로 둘 다 확인합니다.
    final scanGuide = find.text('케어 라벨을 프레임 안에 맞춰 촬영해 주세요');

    for (final target in [find.byIcon(Icons.camera_alt), find.text('스캔')]) {
      await _pumpMainScreen(tester);
      expect(scanGuide, findsNothing);

      await tester.tap(target);
      // 스캔 탭은 카메라를 찾다 테스트 환경에서 예외가 나므로 끝까지 기다리지 않습니다.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      expect(scanGuide, findsOneWidget, reason: '$target');
      await tester.pumpWidget(const SizedBox.shrink());
    }
  });
}

Future<void> _pumpBackButton(WidgetTester tester, ThemeData theme) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: theme,
      home: Scaffold(
        appBar: AppBar(
          leading: AppBackButton(onPressed: () {}, tooltip: '리포트 닫기'),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _pumpMainScreen(WidgetTester tester) async {
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(
          create: (_) => ClosetProvider(storage: FakeClosetStorage()),
        ),
        ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
        ChangeNotifierProvider(create: (_) => NavigationBarOpacityProvider()),
      ],
      child: MaterialApp(theme: AppTheme.light(), home: const MainScreen()),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _pumpCameraView(
  WidgetTester tester, {
  required bool isScanning,
  required VoidCallback onPickFromGallery,
  required VoidCallback onTakePicture,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        body: ScanCameraView(
          cameraController: null,
          selectedImage: null,
          isScanning: isScanning,
          isCameraInitializing: false,
          cameraErrorMessage: null,
          onRetryCamera: () {},
          onPickFromGallery: onPickFromGallery,
          onTakePicture: onTakePicture,
        ),
      ),
    ),
  );
  await tester.pump();
}

/// [target] 을 감싼 가장 가까운 InkWell 입니다.
Finder _inkOf(Finder target) =>
    find.ancestor(of: target, matching: find.byType(InkWell)).first;

/// [icon] 이 든 원을 누르고 있는 동안 원에 칠해지는 누름 효과(강조·물결)가 모두 진한 파랑이고,
/// 아이콘은 그 위에 남는지 봅니다. 끝에 누름을 취소하므로 탭은 일어나지 않습니다.
Future<void> _expectDarkBlueWhilePressed(
  WidgetTester tester,
  Finder icon,
) async {
  final gesture = await tester.startGesture(tester.getCenter(icon));
  // 누른 채 kPressTimeout 이 지나야 눌림이 시작되고, 강조는 200ms 에 걸쳐 짙어집니다.
  await tester.pump(kPressTimeout);
  await tester.pump(const Duration(milliseconds: 300));

  // 효과는 원(Material)의 효과 층에, 아이콘보다 먼저 칠해집니다.
  final inkLayer = Material.of(tester.element(icon)) as RenderObject;
  expect(
    inkLayer,
    paints
      ..rect(color: AppPalette.accentPressed)
      ..paragraph(),
  );
  // 물결은 강조 아래에 깔리지만, 강조가 짙어지거나 옅어지는 동안 비쳐 보이고
  // 빠르게 다시 누르면 강조 위에 새로 쌓이므로 물결도 진한 파랑이어야 합니다.
  expect(inkLayer, _paintsInkOnlyIn(AppPalette.accentPressed));

  await gesture.cancel();
  await tester.pump(const Duration(milliseconds: 300));
}

/// 효과 층이 칠하는 네모·원(누름 강조와 물결)이 모두 [color] 인지 봅니다.
/// 기본 회색 강조·물결이나 Android 반짝이 물결(셰이더로 칠함)이 섞이면 실패합니다.
PaintPattern _paintsInkOnlyIn(Color color) =>
    paints..everything((method, arguments) {
      final paint = method == #drawRect
          ? arguments[1]
          : method == #drawCircle
          ? arguments[2]
          : null;
      if (paint is! Paint) return true;
      if (paint.shader != null) throw '$method 를 셰이더로 칠했습니다';
      // Paint 는 색을 float32 로 담아 double 로 비교하면 어긋나므로 32비트 값으로 봅니다.
      if (paint.color.toARGB32() != color.toARGB32()) {
        throw '$method 를 ${paint.color} 로 칠했습니다';
      }
      return true;
    });

Clothes _clothes(String title, {required int health}) => Clothes(
  title: title,
  category: '상의',
  health: health,
  materials: const {'cotton': 100},
  careInstruction: '찬물 세탁',
  carbonFootprint: 2.1,
);

void _usePhoneView(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
}
