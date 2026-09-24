// Frozen review excerpt from mit-han-lab/omniserve, Apache-2.0.
// Repository commit: 02b2925aa6fa3b92b06316a1524b7f38922cd9c8
// Path: kernels/csrc/qgemm/w4a8_per_group/gemm_cuda.cu
// Blob identifier recorded by the upstream repository: 5d1fb48bd4934dddcd6e66a175910a4d1b3e6ed1
// Only the restricted packed-dequant expression block is retained here.
uint4 loaded = *((uint4 *)(src) + warp_offset_n / 32 * kSmemCol +
                 shared_iter * 32 / 32 * kSmemCol + k_0_1 * INTRIN_K + threadIdx.x);
uint32_t loaded_0 = loaded.x & 0x0F0F0F0F;
uint32_t loaded_4 = (loaded.x & 0xF0F0F0F0) >> 4;
uint32_t loaded_2 = loaded.y & 0x0F0F0F0F;
uint32_t loaded_6 = (loaded.y & 0xF0F0F0F0) >> 4;
uint32_t loaded_1 = loaded.z & 0x0F0F0F0F;
uint32_t loaded_5 = (loaded.z & 0xF0F0F0F0) >> 4;
uint32_t loaded_3 = loaded.w & 0x0F0F0F0F;
uint32_t loaded_7 = (loaded.w & 0xF0F0F0F0) >> 4;

auto ptr = (uint32_t *)dst + shared_iter * 8;
int scales_zeros_offset = warp_offset_n + (threadIdx.x / 4) * 4 + shared_iter * 32;
uint32_t packed_scales = *reinterpret_cast<uint32_t *>(scales_i8 + scales_zeros_offset);
uint32_t packed_zeros = *reinterpret_cast<uint32_t *>(zeros + scales_zeros_offset);

uint32_t scale_0 = packed_scales & 0xFF;
uint32_t zero_point_0 = __byte_perm(packed_zeros, 0, 0x00000000);
uint32_t ptr_0 = loaded_0 * scale_0;
uint32_t ptr_1 = loaded_1 * scale_0;
ptr[0] = __vadd4(ptr_0, zero_point_0);
ptr[1] = __vadd4(ptr_1, zero_point_0);

uint32_t scale_1 = (packed_scales & 0xFF00) >> 8;
uint32_t zero_point_1 = __byte_perm(packed_zeros, 0, 0x00001111);
uint32_t ptr_2 = loaded_2 * scale_1;
uint32_t ptr_3 = loaded_3 * scale_1;
ptr[2] = __vadd4(ptr_2, zero_point_1);
ptr[3] = __vadd4(ptr_3, zero_point_1);

uint32_t scale_2 = (packed_scales & 0xFF0000) >> 16;
uint32_t zero_point_2 = __byte_perm(packed_zeros, 0, 0x00002222);
uint32_t ptr_4 = loaded_4 * scale_2;
uint32_t ptr_5 = loaded_5 * scale_2;
ptr[4] = __vadd4(ptr_4, zero_point_2);
ptr[5] = __vadd4(ptr_5, zero_point_2);

uint32_t scale_3 = (packed_scales & 0xFF000000) >> 24;
uint32_t zero_point_3 = __byte_perm(packed_zeros, 0, 0x00003333);
uint32_t ptr_6 = loaded_6 * scale_3;
uint32_t ptr_7 = loaded_7 * scale_3;
ptr[6] = __vadd4(ptr_6, zero_point_3);
ptr[7] = __vadd4(ptr_7, zero_point_3);
