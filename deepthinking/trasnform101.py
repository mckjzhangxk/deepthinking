# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/00_transformer.ipynb.

# %% auto 0
__all__ = ['batch_dataset', 'padding_fix', 'padding_dynamic']

# %% ../nbs/00_transformer.ipynb 57
def batch_dataset(ds:DatasetDict, #数据集
                  mapping_func #func(example,maxlen)签名的函数
                 ):
    """
    使用`mapping_func`作用于数据集ds上，把转换后的结果返回
    """
    ds=ds.map(padd_func,batched=True)
    ds=ds.remove_columns(['sentence1','sentence2','idx']).rename_column('label','labels')
      # dataset.map返回的数据集，sample是存放在list中的，加上这句话，把list转换成对应的tensor
    ds=ds.with_format('torch')
    return ds

# %% ../nbs/00_transformer.ipynb 60
def padding_fix(example,maxlen=512):
    """
    把example的句子通过`padding`填充的方式，转换成固定`maxlen`长度的tokens，然后返回。
    """
    ret= tokenizer(example['sentence1'],
                   example['sentence2'],
                   padding=True,
                   truncation=True,
                   max_length=maxlen)
    return ret

# %% ../nbs/00_transformer.ipynb 65
def padding_dynamic(example,maxlen=512):
    """
    按照example的句子按照句子的实际长度进行返回。
    """
    ret= tokenizer(example['sentence1'],example['sentence2'])
    return ret
