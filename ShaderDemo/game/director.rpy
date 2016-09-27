
init python:
    import shader

    def findLayer(image, layer):
        if layer:
            return layer
        base = image.split(" ")[0]
        if base in config.layers:
            return base
        return "master"

    #Helper utilities for making showing and managing shader displayables easier.
    #This assumes a certain convention for naming your character sprites.
    #In this case they should be, for example "amy dress smile". And if that
    #image has an influence map associated with it, it should end with " influence"
    #Feel free to modify this to suit your own needs. After all, it's not about
    #what kind of naming etc. conventions you have, but that you have one at
    #all and that it is consistent.

    class CallChain:
        @staticmethod
        def dissolve():
            renpy.with_statement(dissolve)
            return CallChain

        @staticmethod
        def fade():
            renpy.with_statement(fade)
            return CallChain

    def show(image, pixelShader=shader.PS_WIND_2D, uniforms={}, update=None, xalign=0.5, yalign=0.1, layer=None):
        #TODO use **kwargs and pass them to show_screen...
        base = image.split(" ")[0] #For example "amy dress smile" would turn into "amy"
        active = findLayer(image, layer)

        textures = None
        influence = image + " influence"
        if renpy.has_image(influence, exact=True):
            #Has an influence image
            textures = {"tex1" : influence}
        else:
            #No influence image for this image, so use all black zero influence image.
            textures = {"tex1" : "black.png"}

        #Hide the old one (if any) so animation times are reset. This might not be desirable in all cases.
        hide(image, layer=active)

        renpy.show_screen("shaderScreen", image, pixelShader, textures,
            uniforms=uniforms, update=update, xalign=xalign, yalign=yalign,
            _tag=base, _layer=active)
        renpy.show_layer_at([], layer=active) #Stop any animations
        return CallChain

    def hide(image, layer=None):
        base = image.split(" ")[0]
        renpy.hide_screen(base, layer=findLayer(image, layer))
        return CallChain

    def warp(image, xalign=0.5, yalign=0.1, layer=None):
        layer = findLayer(image, layer)
        hide(image, layer=layer).dissolve()
        show(image, xalign=xalign, yalign=yalign, layer=layer).dissolve()
        return CallChain

    def scene(image=None):
        config.scene()
        if image:
            show(image)
        return CallChain

    CallChain.show = staticmethod(show)
    CallChain.hide = staticmethod(hide)
    CallChain.warp = staticmethod(warp)
    CallChain.scene = staticmethod(scene)
