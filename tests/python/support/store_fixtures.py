"""Store fixtures for tests: build a tree and lay a view of it, or seed a
document's result straight into the store without a kernel."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def build_view(
    compound: Any,
    *,
    package_dir: Path,
    root_name: str,
    force: bool = False,
    provenance: Mapping[str, Any] | None = None,
    progress: Any | None = None,
) -> dict[str, Any]:
    """Build ``compound``'s tree into the store and lay a view of it at
    ``package_dir`` (the directory shape the older readers consume). Returns the
    build stats plus the tree hash under ``tree``."""
    from cadgen.store.build import build_tree_from_compound
    from cadgen.store.view import export_view

    tree_hash, _tree, stats = build_tree_from_compound(
        compound,
        root_name=root_name,
        force=force,
        progress=progress,
    )
    export_view(tree_hash, Path(package_dir))
    result = dict(stats)
    result["tree"] = tree_hash
    return result


# Proven small box inputs, generated with the named loaded producer. Keeping
# encoded inputs here lets catalog/security fixtures seed genuine geometry and
# surfaces without importing OCP in the process under test.
FIXTURE_SURFACE_PRODUCER = {'scheme': 19, 'surfFormat': 2, 'build123d': '0.11.1', 'ocp': '7.9.3.1', 'cadqueryOcp': '7.9.3.1.1'}
_GEOMETRY_FIXTURES = [{'kind': 'native', 'codec': 'bintools-v4', 'brep': '0bdb4f63f3ab902a54be4da365fe1810a2cf9fb9f688d452e8a608a8c4328f51', 'faceColors': {}, 'contentHash': '01e2a28516540a13ff82f3e0479e481eb16c24c2f60cad2cb2e518d90eecee41', 'payload': 'eJylVttu00AQXTvXuumFFih3DE8Q8QBpxCN1lSLxgFSkRLxbaRsqRXGUEKTyxHfwE/wAUvsX/EbEFzBOdmYTeyZrB6uKVzuzc87MnB3XOx2eD/zWcbt1fPLe70TDqB/1rvzPzVf+i+5Lf24Nx93w7Nz7GHXDr5fRYOy/9lqT0bfzxtnYbzQ9R7HP9AhXWR2qgeB4LUQwkZION+tyECHyc7BBoCF/HcwJG4ebdTlIzxocsjpkr0PuUtsjBP/NIRVhdkfG/puGdEOys1MJMj+SWAKZ3Aj0SAhS20WE5AFrDrSBjnkR6JEQ5IjJAJY+2A8EeRECG8KnqH/ViwaHJzCF9fp00BldhoPepE/zuT0ZXYRdUN9bm/jSCNn8pte4yi2l1QC5u5A9kETIdntSB/IC5x4AUiCJkHUoC4EsfqbJKYV5nfaXcAgKO2x6lQ+/fv/8++f7Oz5q3ChHOfBXt3jOU5l5ltHTmW3wcV1HSfoDowsvdxWj+PBz3Hum3yLHIJXNEkceSQVuQeQIxiL8FgQjcXyKW0jWxlEpniOPBKUqiRzBWIZXUTCmOT5GjkvI/HkoQEVEBmMVfkuCkZAR0HSwNE9eOb7ecZ6gzyNcPETnoiKeFNyZK+4B+iTKzX3TeIFzF5JrDJ8k1H4DXmXJ6KkMAr+Hewe2bIJUNksceRrQpU2RIxhrKoPA7+AWkrVxjB+OY4UFglJtiRzBuK0yCJw47iPHJeSqkKO7IyKDcVdlEDgCmg6SwO/qHec2+uzh4hY6G4EbGlrgu2wqGyyf6ZEbh+T1BsY9MZW4eToVzMDc1SVkTwq+vwo5zp2X2AIyXQOaoVTEbb1D1VRbuPDR2RTR0NBFrLGpbEpsYx3xYgNjzMBaRNIDP2prwnn3YBVyXB9rEekO4LQ3RcTWOSRAkhHO3IUiGhq6iHh9TEAc0EYUqGiFDVsIaIqmA6LWTUD8Bhh906XBfi8ENLXQAZFyvYAB76PHDnpS03EOmcGO8eou/jeDQqrT9+8fa241eQ==', 'surface': 'eJzNWluPozYUjvpTrD6SCJtLSF46Uqt9rdTLU7WqvMGTYZeBCMhopqNI/Wn9abUZbrYxtmFWQyRmweScgz++75xjZ3//87dPP2w2m9cf6QGeSFEmeQaOyAHlA76QEhz/egV5EYMjdMC3JKMnoMzTJAYOeMrT6yMBx3Dn3j474B6fhO/XLuqzgjDXhA5XxZU44PpEv+juXMejxxbRP/SC+iivBXPzxwuzA5cUZ4QGwgXBdRgHnEhWkaIxhvURULsvX/LnZnB4oLcIvWNwfG1n0TrPi+ScZLwxNXiOk2IwCOvBl35wC7uv/vM22gw4WzZ6c0Ca5xeGBwUkJucahjdkL6RI8jg5geM9TkuKxiVPa+Rcx6fuvmV5xa78+qrA2Zn0YNEREp/Jrw3CPa61q5tjHCviYkEkBUN8MLQkGAy5aMjVTc0TKWMRDPl8sEg3NV8K9pnezvLiEafUon7T254ZF1zgx5IxSUEd/JyUEh/YBPIGyDFdNJNYLgw4Jgw4EAW0FQb8cGF4iHulXqjjT7CAP74gQ1mHAn+iJdLweSEGshCFqe2XRAt4IYayEIW5hdPa4F7tqDSghTQ845LRM29KGJ5QMYLGTlEx2qf6DhVDwKkRxnYQdZ4wQj7XhXKug/z7PCxhz56X4d5OhtYVitdhJOtQmBt0F6g+4nV40OpQoiivjC4VqqUxWjV4TnTS8M2rxlxtoDFtoLlFY2D8Qdo48LkOunKyEwkkv1OLHsf1hXiyGKe6HOueCvJqhFCWozi/ZU0ccoWeUduh7jWd1fAdKyWCDCUSGFWPlm1IqxAkKaR/VEX1kPo16+ohiOFlRAydRIZqmqUQiIRVgKddBviLGOQJkvQtJWkd0Bc06WsXA9GSFBAIkgy0kjwYKGTb1hKLMsJxo5NIaFZFlmrEG9OIN7eK9HnlQzQSClkv1K4H0BIKhYIk97IkJ9sea4nsBU1GdmsC63iRIMlI27NCGVCp1erNJhTiqRXSxFPtX51SXNJ74J7g6lowip7yrEqya1K9sB0x/HhJSfz3Ay7YxlicPJC4wOkvDJIDCwLuU3ymDih5AI6/YiaZT/Tvz/k1q2rATtfiqdVYmtQqYOKgANQoOR59wpRk5+pB7t3aiUzshPXTrwMNNNcEU6STsb5NLPg3g7RE/ZBTVe8tKnITWhfe4QBvMcu501mubVrs8PYGeAu5TNTiNOCeBLiiYfLWhbg/yfDJ1Yk94mj3Pgzn/GgY7q8L70DLcGWvy898TkZZxHAZcJMlwUcjjiZyOOwIM7Fpa57D4Qjicxgu+dEwPFwX3uoc3m6Sczl8gLHQqZrivTiHS450DN+vC3F1Dm8BlRg+vsNkgvh75HDJj4bh0brwVudwuBvJ4WM/A5nl8LGMsojhxjn8sCbEPQ5xuBv7fUFZNfmpz6mawspXXDPZVk3FzzBsQbkmyEMt5JMbDvZLH++9IJfTuAryVa02fQ3L+7Qx8UuBOcvFPD4b8vFEroJ8VQtOX8PyvjIKkNs3K/xi6R0g17KcPRTDoTZv/ptQ2G24QHS7bbrP3d2G+7Dr9uju/zf8QnNs3sbF+0Pb7qOyn4hvZD8R3+j5m8+/P/Hn7TX7l9kP74/5V9l38Tf8tTg2x94k/tTz806F87v+vLYd3G/9D2Mo7YW5ic+njT9hbxRf+fz/A9Hkyf0='}, {'kind': 'native', 'codec': 'bintools-v4', 'brep': '92e6935c58872e596eeda474ad1f8e7dcc4d0c75f4ad9565e332ffc38683671f', 'faceColors': {}, 'contentHash': 'ed085edcb64085e841fec251451ac621ec0789496dc57f816d1eadc03b56df33', 'payload': 'eJylVstu00AUHTvPuumDFihvDCuIWEAasQRXKRILpCIlYm+laagUxVFCkMqK7+An+AGk8hf8RsUXcJ34zMT23My4WFE8mrlzzrl3ztzEO5kMxn7nqNs5On7n96JJNIqGF/6n9gv/Wf+5v1wNZ/3wdOB9iPrhl/NoPPNfep359OugdTrzW23PEdrn6i1GtgH1gAm8ZBAUUjbg93U1sBTFNRgpAibAXAcuoHgdOA3ccw0NtgH2dSheaiNC8N8acgiLOzLzX7W4G2KvTmTEfM9yMWIKM8iHZTAg5xkyG8w5BJl3UQb5sAwsYhbAcA7mDRlp1ht4ho/R6GIYjQ+PqQsn45Nxb3oejofzkezP3fn0LOyT+16bzJdnsIu7usSosJXWExQ+BXsgTpDp9uQ2FCUu3AA4IE6QsSkzQIY4dcg5h3m97udwQg47bHu19z9//fj759sbPWp8UI5w6NM0RC5TWURWEeksJvS4riM4/9GiSy93naJ481PMPUnerMYgl01Ko55JBG6J1UiLZfouMYtS42NMQaxJoxB6jXomKlWF1UiLVXqVmcW8xofQmGLW76cC1FhmWqzTd4VZlMwgVCdYWSYvHD+ZcR4h5gEG9xFcFlKnBHeWjruHmGy5g7SWNQbPRC7ANQejT5Jqv0GvKrfoCQuD38HcgSmbIJdNSqNeBp3SJquRFhvCwuC3MAWxJo3xo9NY0xJRqbZYjbS4LSwMLjXuQ2OKuc7k6O6wzLS4KywMDkJ1gtLgt5MZ5yZi9jC4gWBlcCUjMfiuNpUNTm0Myba5PZtUkIG6qylmjwPfX8cc5260mLwGsofKIm4nM7KaYgsDH8GqiEpGUsSGNpVNTm3sI7Ybxgrs/aBvtQ3tdgI/WMcc18f+nqLbqyLi6BxpQGkj9NyVIioZSRFxfRQgGrQyBRwtcGArgKpoCSC8rgDxG6D8LS8NznsFUNUiAYTkZgmAdxGxg0h56OhDqrEDr+ni3wyM1JS/f/8AfxceIg==', 'surface': 'eJzNmt2OozYUx9E+irWXJAJDCMnVSK32ttK2vapWlTd4MnQZiICMZjrNu/XRajN82cZfMNUQidXEYB/7z/mdc+zsr79//fLJcZx/PjvOK3jCZZUWOThCF1QP6IIrcPzjFRRlAo6+C36kOfkDVEWWJsAFT0V2fcTkDtx6t28uuEcnrkMzRvNXienYmDTX5RW74PpEHvS2nhuQa0MGcMkXMkZ1Lekwv73QfuCSoRwTS6jECBwj8hQ44bzGZdvZb64d6ff9e/HcNo4v+GZhGBgcX7tldIMXZXpOc7Yz6fCcpOWo0W8aX4bGjd8/+vdba9vgbmjrzQVZUVyoHkSQBJ8bGd6kveAyLZL0BI73KKuIGpcia5Tz3JAM9yMvavotbL6VKD/jQSzSgpMz/qVVeNC1GermGtuKGVs+FIxB1hhcYsyPGGvQ0y0t4F3GwhgMWWOxbmmhYOwbuZ0X5SPKSI/mTW8Gz7igEj1W1JMkroOe00rwB7qAohVyiot2EcvBgFNgQA4KKzDgh4MRQOaVBpHOf3YL/CfkMBQ55PwnXoJGyIK4E0HklrZfYm3HghiJIHJri9RsMK92Eg1ogUZgnDKGmZqD4fceK8kY3VT/h4zB6dSCsemS2GwwIjbWRdpYd1jiPXsWw70dhtYZiuUw1nLoewuoj1kOD1oOBRdlyehDoRyNyazB+kSPRmieNeayAafYgNuZSWPU+YPYOLCxzve0wc4X36lFjeOFnD0RRlWVY11T+SyNvi/iyK9vWREHPa5m1Faoe01lNX7HUkSgISI7o+wBjQkJBUKGqUqyh1CvWWcPDoaXCRh6RMY0zSLEh9wuINBuA8JFHhRwSIaWSFobDDkmQ22CjJeEgB2H5E6L5MGAkE2XSyzSCOMbPSKRWRZZykgwxUgwN4sMceVDGIm4qBdp6xC4xIUiDsm9Fkm27LFGZM8xGdvtCaztxRySsRZJXxRUKLWGqkJBSCAnpLUnO786Zagi98A9RvW1pC56KvI6za9p/UKPxNDjJcPJnw+opCdjSfqAkxJlP1NJDtQIuM/QmQxAnAeg5C9EkflC/v2puOZ1I9jpWj51jGVpQwGFgwjQqOQGZIYZzs/1A6kbtvxJmHJfwy6/MTRirjUmCSdTdRuf8G8GYYmMg091c7goiU1wXXpHI72hoLcyynUh1E7vYKQ3F8t4NtSCB4LgkoIpWJfiodLDlbsTe8Xh9n08nBlH4+HhuvTeaT1cWuuyK58TURZ5uCi4yZbgoxWHihgOe4dRHNqax3A4ofgcDxfG0Xh4tC695TG8OyRnYvhIY65SNdV7cQwXBtJ5+H5distjeCeo4OHTJ0wmir9HDBfG0Xh4vC695TEcbidi+NTPQGYxfCqiLPJw4xh+WJPigUJxn1mZ4veF+VmT2/kuzZqSn2HohnJNksvDeLcA5YGD/dYneC/JxTAuk3xVu81Q4+VD2FD8UmDu5Xwcny35dCCXSb6qDWeo8fIhM3KS2xcr7GbpHSTXejmdFNWh6d7+N6GoP3Dx4e3m9J+7O4f50O/d1d//d/xAezlv7fz9cd/+I+uvsG/UX2HfaP7jtqn73TjcfIXxZf0dw/XN6G9k/04+fyP7d44wH6FNZZ8fe+q+yr6qv4l9/tm+7T8SDrpq'}, {'kind': 'native', 'codec': 'bintools-v4', 'brep': '7616b493c09ff73f1a25c48badeafa1330aa0fbc821a6df7f88370fa68fa1915', 'faceColors': {}, 'contentHash': 'bca29d8e668cef75b9fa10687b2f4b3eb1535e5c4b11619bd55255a24e503011', 'payload': 'eJylVstu00AUHTvPuumDFihvDCuIWEAasQRXKRILpCIlYm+laagUxVFCkMqK7+An+AGk8hf8RsUXcJ34zMT23My4WFU8mrlzz7lnzlzXO5kMxn7nqNs5On7n96JJNIqGF/6n9gv/Wf+5v1wNZ/3wdOB9iPrhl/NoPPNfep359OugdTrzW23PEdrn6i1GtgH1gAm8ZDKoTNmA39flwEIU52CCQLnFdWADCuvAcuCea3CwDbDXobDU5gzBf3PIZVjckZn/qsXdEHt2IkPmexaLIVMYQT4cAqcHi5DdYKxBBhiQWAT5cAh8xmwCwzmYN2SoWW/gET5Go4thND48pi6cjE/Gvel5OB7OR7I/d+fTs7BP7nttMl8ewS7u6hKjwlZaD1D4FOwTcYRMtye3oShw4QbAJeIIGbsVk8gQpw455zCv1/0cTshhh22v9v7nrx9//3x7o88as3KEQ39NQ+SylEVkFZHOYkKf13UE5z9adOnlrmMUb36KuSfJm+UY5KpJcdQjicAtsRxpsUy/JWZRcnyMKZA1cRRCz1GPRFJVWI60WKVXmVnMc3wIjilk/X4SoMYi02KdfivMokQGoDrByrJ44fjJjPMIMQ8wuI/gspA8ZXJn6bh7iMnIrfum6Q2uu5C6g9EXSdpv0KvKLXrCwuB3MHdgqibIVZPiqKdBp7TJcqTFhrAw+C1MgayJY/zoONa0QCTVFsuRFreFhcElx31wTCHXmRrdHRaZFneFhcEBqE5QGvx2MuPcRMweBjcQrAyuaCQG39WWsqHlQzrFKTm/uXtsKSsiogJ1V1PIHpd8fx1yXDvX2fLXQPZQKeJ2MiPVFFsY+AhWIioaiYgNbSmbHNvYR5zZ3JiBUUTpB32rbTD73YN1yLE+RhHlHUC3VyLi6BxpQGkj9NwVERWNRERcH5UQDVqZAo4WOLCVhEq0JCG8rhLiG6D8LS8NznslodIiSQjKzRIS3kXEDiLloaMPqcaOfE0X/83ASE35/fsHBFke6g==', 'surface': 'eJzNWl2PozYUjfanWH0kEdiEkDxFarWvK7Xdp2pVeYMnQ5eBCMhoprP5b/1ptRm+/IUxRBoiMUpM7r324Zx7r5354+vvnz+tVqufv6xWb+CZ5EWcpeAAHVA84gspwOGvN5DlETh4DvgRp/QNKLIkjoADnrPk+kTonXDj3r454AGfBIPKR/UuJ8w3ocNlfiUOuD7TL7ob10H0WkP6h36gPoprztz8+crswCXBKaGRcE4wOAT0W+BE0pLktbFXXVtq9/179lIP9i/4HqFzDA5vzTIa51ken+OUN6YGL1Gc9wa9avC1G1x77Vf/fR+tB5w1G705IMmyC8ODAhKRcwXDO7QXksdZFJ/A4QEnBUXjkiUVcq7jU3c/0qxkn/zqU47TM+nAoiMkOpMvNcIdrpWrmzM6VsjF8qAUDPLB4JxgXsBFg65paUikjEUw6PPBQtPSfCnYN3o7zfInnFCL6kmvO2ZccI6fCsYkDXXwS1xIfGALyGogVbqoFzFfGEglDNQTBbIVBvpwYSDIPVIUmPizncEfX5ChrEOBP+Ecafi8ELeyEIWl7eZE2/JCDGQhCmsLhrXBPVqlNJCFNNDokuGK/FUKY88JgwqiZqymYigd36diCDjVwlg3RWyyMAI+1wVyrhPYs5/Dnh0vw52dDK0rFK/D0FwP3RmqD3kd7o06lCjKK6NNhXppKKsGz4lWGv74qjFVG1ClDTi1aPSMP0gbez7Xea6x6/DkZ2rR47i+EM8oRjSrp/J4NXqeUY7evCYOukLPaFTkztBZ9Z+xViJwpES2VtUDWrZVTCHdVDXVQ+rXrKuHIIZXhRhaifTVNEkhHhR2Aci4DfBnMQgJkvQtJWkd0Bc06Rs3A+GcFLAVJLk1SnI/QiHrppZYlBGOG61EArsqMlUjSKURNLWKdKh9iEYCIesFxv0AnEOhQJDkztyIuLMkshM0GdrtCazjhYIkQ2OZ9GRApVar6yoGFIL0Cqnj6c6vTgku6D3wQHB5zRlFT1laxuk1Ll/ZkRh+uiQk+vsR5+xkLIofSZTj5DcGyZ4FAQ8JPlMHlDwAR/9gJpnP9O+v2TUtK8BO1/y50VgSVypg4qAAVCg5iM4wIem5fKR9w0Y8CRvc1/DLrwL1NFcH06QTVd8mPqrbiLRE/ZBTWR0uanITXBbeQQ9vKOE9mOWapsUOb9TDW8hlohaHAUcS4JqGCS0LcX+Q4YO7E3vE4eY+DOf8GBjuLwvvrZHh2l6XX/mUjDKL4TLgY7YEH404HMjhqCXMwKHt+ByOFIhPYbjkx8DwYFl463N4c0jO5fAexkKnOhbv2TlccmRi+G5ZiOtzeAOoxHD1CdMYxO+RwyU/BoaHy8Jbn8PRRpHDVT8Djcvhqowyi+Gjc/h+SYgjDnGe4c3vC9qqyS99StUUdr5zG3HNzzBsQ7kkyAMj5IMHDvZbH3QvyOU0roN8UbtN38DyLm0M/FIwnuViHp8MuTqR6yBf1IbTN7C8q4wC5PbNCr9ZugPkRpazSTEcKvP634SC9sDFg7fbqn0djyvuxT43V3v/v/4X6mv1Pi7e79u2L539QPxR9gPxR81fMQfRVpyPyr/OXvStuj8Uf8h+TPyh+fNOhffH7v3xyN9X4quzH5j/qPgD9qPiH3Xz/x8cc8LX'}, {'kind': 'native', 'codec': 'bintools-v4', 'brep': '26411db2df8fa77051b37dfbed5925185810d476a1d9a555a0ca36ad058fdf45', 'faceColors': {}, 'contentHash': 'cbccb6aabd344d5ca5314286fa349e93ba29d7162354f7b55790f62395ac9f9d', 'payload': 'eJylVs1u00AQXju/ddPWtED5x3CCiAOkEUdwlSJxQCpSIu5W2oZKURwlBKmceA5eghdAKm/Ba1Q8AePEM5vYM9l1sap4tTM73zcz347rHY9PR0HnsNs5PHoX9OJxPIwHF8Gn9ovgWf95sLBG0350cup9iPvRl/N4NA1eep3Z5Otp62QatNqeo9jn6i2ubB3qoeB4KUTQkbIOv6/LQYQozsEE4YeCg7EOvuRQuA4iB+m5BgdbB/s6FC61OUL43xxyEeZ3ZBq8akk3xJ6dypD5nsUSyBRGoEdCkNouImQPGHOgAwYkEYEeCUGOmA1g6IP5QIaa9QEZ4WM8vBjEo4MjmMLp+njUm5xHo8FsSPO5O5ucRX1Q32uT+PIIdn5Xl7gqLKX1AIW7YB9IImS6PbkDRYELDwApkETIOJSFQAY/3eScwrxe93M0BoUdtL3a+5+/fvz98+0NHzVplKMc+GsaPBepzD2r6OnMN/i4rqMk/YHRhZe7jlFy+CnuPUnfIscwl80KRx5JhW5J5AjGMvyWBCNxfIxbSNbEUSmeI48EpaqIHMFYhVdZMOY5PkSOK8j8eShATUQGYx1+K4KRkBFQd7CySF45QbrjPEKfB7i4j85lRTwpuLNQ3D30yZSb+6bxAucuJNcYPkmo/Qa8qpLRUxYCv4N7+6Zswlw2Kxx5GtClTZEjGBvKQuC3cAvJmjgmD8exxgJBqbZEjmDcVhYCJ457yHEFuS7k6O6IyGD0lYXAEVB3kAR+O91xbqLPLi5uoLMWuKaRCtxnU9lg+fihm4Tk9QbGXTEVX6eCGei7uoLsScH31iEnufMSW0Kma0AzlIq4ne5QNdUWLgJ01kXUNNIiNthUNiW2iY54sYExYWAsIumBH7UN4by7vw45qY+xiHQHcNrrImLrHBIgyQhn7lIRNY20iHh9dEAc0FoUqGiFDVsKqIuWBkSt64D4DdD6pkuD/V4KqGuRBkTKzRIGvIseO+hJTcc5pAc7xmu6+N8MCqlJ379/iYwfsg==', 'surface': 'eJzNWl2PozYURf0p1j6SCIxDSJ4itdrXSrvtU7WqvMGToctABMlopqNU89P602ozfNnG2IaphkiMwOB77cM5916b+fr7l88/OY7zzyfHeQGPpCiTPAN76ILyHp9JCfZ/vIC8iMHed8GPJKMnoMzTJAYueMzT6wOhD6O1d/vmgjt8FDpUNqqzgjDbhDZfiitxwfWRPuitPTegxwrSP/SC2iivBTPz2zPrB84pzgj1hAuCwT6kT4EjyS6kqDv71bGh/b5/z5/qxv4B3zx0hsH+pZlGYzwvklOS8Z1ph6c4KXqNftX43DWu/PbRv99a6wZ3xVpvLkjz/MzwoIDE5FTB8AbtmRRJHidHsL/DaUnROOdphZznImruR5Zf2BWqrgqcnUgHFm0h8Yn8WiPc4VqZurnGviLOlw8lZ5B3Buc480POG/R0UwtEylg4g4h3FummhiRn3+jtLC8ecEp7VG961THjjAv8UDImKaiDn5JS4gObQF4DOaSLehLzhYGGhIF6okC2wkAfLowAcq80CHX82czgDxJkKOtQ4E80RxqIF+JGFqIwte0cbxteiKEsRGFu4bg2uFc7KA1kIY3AOGXUPNYIw4ecMmBLWUXKaMb6P6QMAahaGasmi01WRsgHu1AOdoh/obs59NnyOtza6dA6RfFCjGQhCnPzvRmyj3gh7rRClDjKS6ONhWptDKYNnhOtNpB52pgsDjgkDriemDZ6nT9IHDs+2vmeHO5EBskv1aLK8ZDgT1bjWJ1jXVX5vBx9X9ajOL95ZRz0hKpRW6NuNbVV/x0rNQINNbIxyh9NlIdaiUSSQrqhKtKHVLFZpw9BDM8DYmgl0lfTJIX4UFgHBNqFAJrFoECQJLKUpLVDJGgSaZcD0ZwQsBEkudFKcmegkFWTTCzyCMeNViKhWRqZq5FgSCPB1CzSxZUP0UgoRL1QuyKAcygUCpLcypIcrXusJbIVNBnZrQqs/UWCJCNt0erLgEq1VldVjCgkUCuk9qfawTqmuKT3wB3Bl2vBKHrMs0uSXZPLM9sUww/nlMR/3uOC7Y3FyT2JC5z+wiDZMSfgLsUnaoCSB+D4L8wk85n+/Tm/ZpcKsOO1eGw0liaVCpg4KAAVSm5AR5iS7HS5p3XDWtwLG13Y8NOvHPU0VztThJOhuk1M+DeDsETtkOOl2l5UxCa4LLzDHt5Qwns0yjVFix3eQQ9vIZaJWhwHPJAAVxRMwbIQR6MMH12d2CMO1+/DcM6OhuFoWXhvtAxX1rr8zKdElFkMlwE3WRJ8NOJwJIajljAj27bmMRwNID6F4ZIdDcPDZeGtjuHNNjkXw3sYC5WqKd6zY7hkSMfw7bIQV8fwBlCJ4cM7TCaIv0cMl+xoGB4tC291DEfrgRg+9CHILIYPRZRZDDeO4bslIR5wiKP10AcGZdbkpz4laworX3HNZJs1FR9i2IJySZCHWshHNxzslz7Be0Euh3EV5ItabSINy7uwMfKlwJzlYhyfDPlwIFdBvqgFJ9KwvMuMAuT2xQq/WHoHyLUsZ4NiOFTd638UCtsNFx/ebk77Oxwc7seum6O9/2//gfpw3trF+/2+7U/Vf8S/Uf8R/0bjr3+vB/68uX6t7fTvD9lX9W/9O/y12Dalv4n/sfHzRoXzQ3f+euDvN/b7PpT9Hd63OD6t/5H+Rv4PqvH/B6pNy0M='}]

def seed_result(
    document: Path | str,
    descriptor: Mapping[str, Any] | None = None,
    *,
    model: Path | str | None = None,
    surf: bytes = b"SURF\x00",
    components: tuple[str, ...] = ("c0",),
    kind: str = "assembly-package",
    entry_kind: str = "part",
    sidecar: Mapping[str, Any] | None = None,
) -> str:
    """Seed geometry and an optional surface derivation without native imports.

    Caller aliases are remapped to genuine geometry CIDs. The historical default
    SURF sentinel selects valid fixture bytes; other payloads deliberately test
    corrupt disposable surfaces. Explicit malformed structure/geometry overrides
    stay malformed so completeness checks can reject them.
    """
    import base64
    import copy
    import zlib
    from cadgen._internal.component_package import canonical_json_bytes
    from cadgen.store.index import write_entry
    from cadgen.store.objects import is_object_hash, put_object
    from cadgen.store.records import note_document_tree, note_output, write_record
    from cadgen.store.surfaces import _expected
    from cadgen.store.trees import TREE_KIND, TREE_SCHEMA, tree_kind

    document = Path(document)
    descriptor = copy.deepcopy(dict(descriptor or {}))
    raw_components = descriptor.get("components")
    if not isinstance(raw_components, dict):
        raw_components = {cid: {} for cid in components}
    if len(raw_components) > len(_GEOMETRY_FIXTURES):
        raise ValueError("seed_result supports at most four independent fixture components")
    tree_components, aliases, component_colors = {}, {}, {}
    for index, (alias, raw_entry) in enumerate(raw_components.items()):
        fixture = _GEOMETRY_FIXTURES[index]
        payload = zlib.decompress(base64.b64decode(fixture["payload"]))
        entry = {name: copy.deepcopy(fixture[name]) for name in ("kind", "codec", "brep", "faceColors", "contentHash")}
        put_object(payload)
        raw_entry = dict(raw_entry or {})
        if raw_entry.get("color") is not None:
            entry["color"] = raw_entry["color"]
            component_colors[alias] = raw_entry["color"]
        if "brepObject" in raw_entry:
            entry["brep"] = raw_entry["brepObject"]
        cid = entry["contentHash"][:16]
        aliases[alias] = cid
        tree_components[cid] = entry
        surface = zlib.decompress(base64.b64decode(fixture["surface"])) if surf == b"SURF\x00" else surf
        surface_hash = put_object(surface)
        if is_object_hash(raw_entry.get("surfObject")):
            surface_hash = raw_entry["surfObject"]
        expected = _expected(entry, FIXTURE_SURFACE_PRODUCER)
        write_entry("surface", expected["surfaceInput"], {**expected, "object": surface_hash})
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    occurrences = descriptor.get("occurrences")
    if not isinstance(occurrences, list):
        occurrences = [{"id": f"o1.{i}" if len(aliases) > 1 else "o1", "name": alias,
                        "component": cid, "transform": identity}
                       for i, (alias, cid) in enumerate(aliases.items(), 1)]
    else:
        for occurrence in occurrences:
            occurrence["component"] = aliases.get(occurrence.get("component"), occurrence.get("component"))
    children = [{"id": occurrence["id"], "name": occurrence.get("name", occurrence["id"]),
                 "nodeType": "part", "children": []} for occurrence in occurrences]
    assembly = descriptor.get("assembly")
    if not isinstance(assembly, dict):
        root = children[0] if len(children) == 1 and children[0]["id"] == "o1" else {
            "id": "o1", "name": descriptor.get("label") or "model", "nodeType": "assembly", "children": children}
        assembly = {"root": root}
    tree = {"kind": TREE_KIND, "schemaVersion": TREE_SCHEMA,
            "label": descriptor.get("label") or "model", "units": "mm",
            "components": tree_components, "occurrences": occurrences, "links": [],
            "assembly": assembly, "stats": {"occurrenceCount": len(occurrences), "linkCount": 0}}
    tree["entryKind"] = tree_kind(tree)
    if descriptor.get("kind") not in (None, kind):
        tree["kind"] = descriptor["kind"]
    for key in ("bbox", "capabilities", "edgeRendering", "color"):
        if key in descriptor:
            tree[key] = descriptor[key]
    # Deliberately malformed fixture knobs must remain malformed; production
    # publication goes through put_tree and native preparation instead.
    tree_hash = put_object(canonical_json_bytes(tree))
    try:
        sha = hashlib.sha256(document.read_bytes()).hexdigest()
    except OSError:
        sha = ""
    owner = Path(model) if model is not None else document
    record = {"entryKind": tree["entryKind"], "sourceKind": "python" if model is not None else "step",
              "tree": tree_hash, "closure": {"hash": sha, "files": [], "static": True}, "children": [],
              "outputs": {str(document.resolve()): {"sha256": sha}}, "stepHash": sha}
    if sidecar:
        record.update(sidecar)
    write_record(owner, record)
    if sha:
        note_document_tree(sha, tree_hash, kind="step", surface_producer=FIXTURE_SURFACE_PRODUCER)
    if model is not None:
        note_output(document, owner)
    return tree_hash


def read_view_descriptor(view_dir: Path | str) -> dict[str, Any]:
    return json.loads((Path(view_dir) / "assembly.json").read_text(encoding="utf-8"))
