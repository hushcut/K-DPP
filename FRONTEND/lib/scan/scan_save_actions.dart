part of '../scan_screen.dart';

/// 결과 검증, 서버 탄소 계산, 옷장 저장과 세션 만료 처리를 담당합니다.
extension _ScanSaveActions on _ScanScreenState {
  /// 세션 만료 시 작성한 의류를 기기에 보존한 뒤 재로그인을 안내합니다.
  /// 저장이 실패해도 저장 버튼이 잠긴 채 남지 않도록 상태를 되돌립니다.
  Future<void> _saveLocallyAfterSessionExpiry({
    required ClosetProvider provider,
    required String? ownerKey,
    required Clothes clothes,
  }) async {
    var isSaved = false;
    var isInCurrentCloset = false;

    try {
      isInCurrentCloset = await provider.addClothesForOwner(ownerKey, clothes);
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

    // 기다리는 사이 계정이 바뀌었으면 원래 계정 옷장에 넣었으니 지금 계정에 안내하지 않습니다.
    if (!mounted || (isSaved && !isInCurrentCloset)) return;

    if (!isSaved) {
      AppBanner.of(
        context,
      ).show('의류를 기기에 저장하지 못했어요. 다시 시도해 주세요.', kind: AppBannerKind.failure);
      return;
    }

    await SessionExpiryHandler.handle(
      context,
      message: '로그인이 만료됐어요. 의류는 기기에 저장했어요.',
    );
  }

  /// 서버 계산 없이 저장해야 하는데 앱 소재표에도 없는 소재가 있으면 저장을 막습니다. 저장하면
  /// 근거 없는 기본계수 값이 옷장·홈 합계·서버 백업에 섞입니다(협의안 T5, DECISIONS 288).
  /// 온라인에서도 저장되지 않는 옷이라 잃는 것이 없고, 입력은 그대로 둡니다.
  bool _blockSaveWithoutCarbonBasis(Map<String, double> materials) {
    final unknown = ClothingEstimator.materialsWithoutFactor(materials.keys);

    if (unknown.isEmpty) return false;

    if (mounted) {
      _updateState(() {
        _isSaving = false;
      });
      AppBanner.of(context).show(
        CarbonApiException.unknownMaterialsMessage(unknown),
        kind: AppBannerKind.failure,
      );
    }

    return true;
  }

  /// 입력 검증 후 서버 계산을 시도합니다. 서버가 입력을 거절하면(400/422) 저장하지 않고,
  /// 그 밖의 실패는 로컬 추정값으로 저장합니다. 다만 앱 소재표에 없는 소재는 추정할 근거가
  /// 없으니 서버가 받아 주지 않으면 저장하지 않습니다.
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
      category: _selectedClothingType.category,
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
        AppBanner.of(context).show(message, kind: AppBannerKind.failure);
        return;
      case ScanSaveSuccess(:final clothes):
        _updateState(() {
          _isSaving = true;
        });

        final provider = Provider.of<ClosetProvider>(context, listen: false);
        var clothesToSave = clothes;
        String? fallbackMessage;
        final accessToken = provider.accessToken;
        // 계산을 기다리는 사이 로그아웃하거나 다른 계정으로 바뀌어도 이 계정 옷장에 넣도록,
        // 기다리기 전에 주인을 잡아 둡니다(C26, DECISIONS 2026-10-14).
        final ownerKey = provider.closetOwnerKey;

        if (accessToken != null && !provider.isAuthenticated) {
          if (_blockSaveWithoutCarbonBasis(editedMaterials)) return;

          await _saveLocallyAfterSessionExpiry(
            provider: provider,
            ownerKey: ownerKey,
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
              clothingTypeId: _selectedClothingType.id,
              weightGram: _selectedClothingType.isDirectWeight
                  ? _selectedClothingType.estimatedWeightGram
                  : null,
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
              weightSource: calculation.weightSource,
              calculationScope: calculation.calculationScope,
              calculationBasis: calculation.calculationBasis,
              calculationSource: calculation.calculationSource,
              calculationNote: calculation.calculationNote,
            );
          } on CarbonApiException catch (error) {
            if (error.type == CarbonApiErrorType.unauthorized) {
              if (_blockSaveWithoutCarbonBasis(editedMaterials)) return;

              await _saveLocallyAfterSessionExpiry(
                provider: provider,
                ownerKey: ownerKey,
                clothes: clothesToSave,
              );
              return;
            }

            if (error.type == CarbonApiErrorType.badRequest ||
                error.blocksLocalEstimate) {
              // 서버가 계산할 수 없는 입력이라고 거절했으니 근거 없는 임시값으로 저장하지 않고,
              // 입력을 그대로 둔 채 고치거나 다시 찍게 합니다(AI 연동 협의안 R1). 아래 저장
              // 구간의 finally 에 닿지 않으므로 여기서 저장 버튼을 풉니다.
              if (mounted) {
                _updateState(() {
                  _isSaving = false;
                });
                AppBanner.of(
                  context,
                ).show(error.userMessage, kind: AppBannerKind.failure);
              }
              return;
            }

            if (_blockSaveWithoutCarbonBasis(editedMaterials)) return;

            // 인증 오류·입력 거절 외의 서버 실패는 아는 소재의 로컬 저장을 막지 않습니다.
            fallbackMessage = error.userMessage;
          }
        }

        var isInCurrentCloset = false;

        try {
          isInCurrentCloset = await provider.addClothesForOwner(
            ownerKey,
            clothesToSave,
          );
        } catch (error) {
          // Provider가 목록을 되돌리므로 실패를 알리고 화면에 머무릅니다.
          debugPrint('옷장 저장에 실패했습니다: $error');

          if (mounted) {
            AppBanner.of(context).show(
              '의류를 저장하지 못했어요. 잠시 후 다시 시도해 주세요.',
              kind: AppBannerKind.failure,
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

        // 원래 계정 옷장에 넣었으면 지금 계정의 리포트를 열지 않습니다.
        if (!mounted || !isInCurrentCloset) return;

        if (fallbackMessage != null) {
          // 저장은 됐고 탄소량만 임시 추정값으로 대신했으므로 안내다.
          AppBanner.of(context).show(fallbackMessage, kind: AppBannerKind.info);
        }

        // 메인 화면은 그대로 두고 이 화면을 새 촬영 상태로 되돌린 뒤, 이 화면을 담은 라우트가 그 위에
        // 리포트를 엽니다. 리포트를 닫으면 바로 다음 옷을 찍고, 이 화면까지 닫으면 들어왔던 탭과 옷장
        // 검색어가 그대로 있습니다. 예전처럼 /main 을 새로 만들면 홈에서 다시 시작했습니다(C04,
        // DECISIONS 2026-10-14). 저장 중엔 설정·"<"·뒤로가기가 막혀 있어 이 화면이 맨 위입니다.
        _clearScanResult();
        widget.onSaved(clothesToSave);
    }
  }
}
