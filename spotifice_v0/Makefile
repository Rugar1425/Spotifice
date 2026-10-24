.PHONY: check-slice test clean

check-slice:  check-spotifice_v0.ice

check-%.ice: %.ice
	slice2html -I /usr/share/ice/slice $< --output-dir /tmp

test:
	clear
	for t in test/test_*.py; do \
		pytest -v $$t || exit 1; \
	done

media: portal2-ost.zip
	mkdir -p media
	unzip -o $< -d media

portal2-ost.zip:
	wget http://media.steampowered.com/apps/portal2/soundtrack/Portal2-OST-Complete.zip -O $@

clean:
	$(RM) -r Spotifice spotifice*.py *.html __pycache__ .pytest_cache .ruff_cache

define run_target
run-$(1): media_$(1).py $(1).config
	./$$< --Ice.Config=$$(word 2,$$^)
endef

$(eval $(call run_target,render))
$(eval $(call run_target,provider))
$(eval $(call run_target,control))
