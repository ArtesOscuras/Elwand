# Build the upstream Linux rt2x00 + rt2800usb driver (unmodified) against the macOS compat layer.
SRC := ../rt2x00
CFLAGS := -MMD -MP -O2 -g -w -fno-strict-aliasing -fms-extensions -DKBUILD_MODNAME='"rt2800usb"' -Icompat -Icompat/uapi -I$(SRC) -Ihost \
 -DCONFIG_RT2X00_LIB_CRYPTO -DCONFIG_RT2X00_LIB_FIRMWARE -DCONFIG_RT2X00_LIB_USB -DCONFIG_RT2800_LIB -DCONFIG_RT2800USB_RT33XX -DCONFIG_RT2800USB_RT35XX -DCONFIG_RT2800USB_RT3573 -DCONFIG_RT2800USB_RT53XX -DCONFIG_RT2800USB_RT55XX -DCONFIG_RT2800USB_UNKNOWN
RT := rt2x00config rt2x00crypto rt2x00dev rt2x00firmware rt2x00link rt2x00mac rt2x00queue rt2x00usb rt2800lib rt2800usb
HOST := ksupport mm_core mlme datapath supplicant sae daemon airport_bridge main mt_glue
SYSHOST := usb_shim crypto net net6 ecp256
OBJ := $(addprefix build/rt_,$(addsuffix .o,$(RT))) $(addprefix build/host_,$(addsuffix .o,$(HOST))) $(addprefix build/sys_,$(addsuffix .o,$(SYSHOST)))

$(OBJ): | build
build:
	mkdir -p build

all: rt2800d
rt2800d: $(OBJ)
	clang -o $@ $(OBJ) -lpthread -framework CoreFoundation -framework IOKit
install: rt2800d
	cp rt2800d ../../rt2800d
	chmod 755 ../../rt2800d
build/rt_%.o: $(SRC)/%.c
	clang $(CFLAGS) -include compat/rt_extra.h -c $< -o $@
build/host_%.o: host/%.c
	clang $(CFLAGS) -c $< -o $@
build/sys_%.o: host/%.c
	clang $(CFLAGS) -c $< -o $@
clean:
	rm -f build/*.o build/*.d rt2800d

-include $(wildcard build/*.d)
