import brut.androlib.src.SmaliBuilder;
import brut.directory.ExtFile;

import java.io.File;

/**
 * Сборка dex из smali-дерева без aapt2 и без пересборки ресурсов.
 *
 *   java -cp apktool.jar DexOnly.java <каталог smali> <выходной dex> [apiLevel]
 *
 * Нужен потому, что apktool b на этом окружении падает в стадии сборки
 * ресурсов (aapt2 отдаёт SIGILL). Ресурсы в этом задаче не меняются,
 * поэтому собирается только dex, а в исходный APK подставляются dex-файлы.
 */
public class DexOnly {
    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("usage: DexOnly <smali dir> <out dex> [apiLevel]");
            System.exit(2);
        }
        int apiLevel = args.length > 2 ? Integer.parseInt(args[2]) : 35;
        SmaliBuilder.build(new ExtFile(args[0]), new File(args[1]), apiLevel);
        System.out.println("dex -> " + args[1]);
    }
}
