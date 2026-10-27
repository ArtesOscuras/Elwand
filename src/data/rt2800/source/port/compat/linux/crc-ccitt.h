#pragma once
#include <stdint.h>
#include <stddef.h>
/* same as Linux: reflected CRC-16/CCITT (poly 0x8408, LSB first) */
static inline uint16_t crc_ccitt(uint16_t crc, const uint8_t *buf, size_t len)
{
	while (len--) {
		crc ^= *buf++;
		for (int i = 0; i < 8; i++) crc = (crc & 1) ? (crc >> 1) ^ 0x8408 : crc >> 1;
	}
	return crc;
}
