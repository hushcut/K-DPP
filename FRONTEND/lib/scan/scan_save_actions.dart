part of '../scan_screen.dart';

/// 결과 검증, 서버 탄소 계산, 옷장 저장과 세션 만료 처리를 담당합니다.
extension _ScanSaveActions on _ScanScreenState {
  /// 세션 만료 시 작성한 의류를 기기에 보존한 뒤 재로그인을 안내합니다.
  /// 저장이 실패해도 저장 버튼이 잠긴 채 남지 않도록 상태를 되돌립니다.
  Future<void> _saveLocallyAfterSessionExpiry({
    required ClosetProvider provider,
    required Clothes clothes,
  }) async {
    var isSaved = false;

    try {
      await provider.addClothes(clothes);
      isSaved = true;
    } catch (error) {
      debugPrint('세션 만료 후 로컬 저장에 실패했습니다: $error');
    } finally {
      if (mounted) {
        _updateState(() {
          _isSaving = false;
        });
      }
    }

    if (!mounted) return;

    if (!isSaved) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('의류를 기기에 저장하지 못했어요. 다시 시도해 주세요.')),
      );
      return;
    }

    await SessionExpiryHandler.handle(
      context,
      message: '로그인 세션이 만료되어 의류는 기기에 저장했어요. 다시 로그인해 주세요.',
    );
  }

  /// 입력 검증 후 서버 계산을 시도하고 실패 시 로컬 추정값으로 저장합니다.
  Future<void> _submitClothes() async {
    if (_isSaving) return;

    _updateState(() {
      _hasTriedSubmit = true;
    });

    final isFormValid = _formKey.currentState?.validate() ?? false;

    if (!isFormValid) return;

    final editedMaterials = _materialInputs.collectEditedMaterials();

    final saveResult = _scanSaveService.buildClothes(
      title: _titleController.text,
      category: _selectedCategory,
      materials: editedMaterials,
      careInstruction: _scannedCare,
      clothingType: _selectedClothingType,
      originalMaterials: _originalScannedMaterials,
      serverHealth: _serverHealth,
      serverCarbonFootprint: _serverCarbonFootprint,
      serverWeightGram: _serverWeightGram,
      serverCalculationMethod: _serverCalculationMethod,
    );

    switch (saveResult) {
      case ScanSaveFailure(:final message):
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(message)));
        return;
      case ScanSaveSuccess(:final clothes):
        _updateState(() {
          _isSaving = true;
        });

        final provider = Provider.of<ClosetProvider>(context, listen: false);
        var clothesToSave = clothes;
        String? fallbackMessage;
        final accessToken = provider.accessToken;

        if (accessToken != null && !provider.isAuthenticated) {
          await _saveLocallyAfterSessionExpiry(
            provider: provider,
            clothes: clothesToSave,
          );
          return;
        }

        if (accessToken != null) {
          // 유효한 세션이면 서버 계산값과 저장 ID로 로컬 초안을 보강합니다.
          try {
            final calculation = await _carbonApiService.calculate(
              materials: editedMaterials,
              minWeightGram: _selectedClothingType.minWeightGram,
              maxWeightGram: _selectedClothingType.maxWeightGram,
              accessToken: accessToken,
            );

            clothesToSave = clothes.copyWith(
              carbonFootprint: calculation.carbonFootprint,
              carbonFootprintSource: CarbonFootprintSource.server,
              carbonFootprintMin: calculation.carbonFootprintMin,
              carbonFootprintMax: calculation.carbonFootprintMax,
              minWeightGram: calculation.minWeightGram,
              maxWeightGram: calculation.maxWeightGram,
              savedResultId: calculation.savedResultId,
            );
          } on CarbonApiException catch (error) {
            if (error.type == CarbonApiErrorType.unauthorized) {
              await _saveLocallyAfterSessionExpiry(
                provider: provider,
                clothes: clothesToSave,
              );
              return;
            }

            // 인증 오류 외의 서버 실패는 로컬 저장을 막지 않습니다.
            fallbackMessage = error.userMessage;
          }
        }

        try {
          await provider.addClothes(clothesToSave);
        } catch (error) {
          // Provider가 목록을 되돌리므로 실패를 알리고 화면에 머무릅니다.
          debugPrint('옷장 저장에 실패했습니다: $error');

          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('의류를 저장하지 못했어요. 잠시 후 다시 시도해 주세요.'),
              ),
            );
          }
          return;
        } finally {
          if (mounted) {
            _updateState(() {
              _isSaving = false;
            });
          }
        }

        if (!mounted) return;

        if (fallbackMessage != null) {
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(SnackBar(content: Text(fallbackMessage)));
        }

        Navigator.pushReplacementNamed(
          context,
          '/main',
          arguments: MainScreenArguments(initialIndex: 1, showReport: true),
        );
    }
  }
}
